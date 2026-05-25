"""WebUI route handlers extracted from main.py.

All methods delegate attribute access to the plugin instance via ``self._p``.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from pathlib import Path
from typing import Any

try:
    from astrbot.api import logger  # type: ignore
except ImportError:
    import logging as _logging

    logger = _logging.getLogger("astrbot_plugin_sylanne")  # type: ignore


class WebUIRoutes:
    """Encapsulates all WebUI HTTP route handlers for the Sylanne plugin."""

    def __init__(self, plugin: Any) -> None:
        self._p = plugin

    # ------------------------------------------------------------------
    # Memory settings & lineage observatory
    # ------------------------------------------------------------------

    async def memory_settings_get_handler(self) -> dict[str, Any]:
        return await self._p._sylanne_memory_settings_page_payload()

    async def memory_settings_post_handler(self) -> dict[str, Any]:
        from quart import request as quart_request

        body = await quart_request.get_json(silent=True) or {}
        return await self._p._update_sylanne_memory_settings_from_page(body)

    async def lineage_observatory_handler(self) -> dict[str, Any]:
        session_key = "default"
        return self._p._sylanne_lineage_observatory_page_payload(session_key)

    # ------------------------------------------------------------------
    # WebUI page & state
    # ------------------------------------------------------------------

    async def page_handler(self) -> Any:
        """Return the full WebUI HTML page."""
        from quart import Response

        # WEBUI_HTML is a module-level constant in main.py; access via plugin module
        import main as _main_mod

        html = getattr(_main_mod, "WEBUI_HTML", "<html><body>unavailable</body></html>")
        return Response(html, content_type="text/html; charset=utf-8")

    async def state_handler(self) -> dict[str, Any]:
        """Return full state JSON for the WebUI dashboard."""
        logger.info("Sylanne WebUI: /api/state handler HIT")
        from quart import request as quart_request

        requested_session = str(quart_request.args.get("session") or "").strip()
        all_sessions = self._p._known_webui_sessions(requested_session)
        # For overview (empty/default), use the most recently active session
        if (
            not requested_session
            or requested_session == "default"
            or requested_session not in all_sessions
        ):
            # Find session with highest tick count (most active)
            best_session = "default"
            best_ticks = -1
            for sk, h in (getattr(self._p, "_hosts", {}) or {}).items():
                ticks = getattr(h.kernel.computation, "_tick_count", 0)
                if ticks > best_ticks:
                    best_ticks = ticks
                    best_session = sk
            session_key = (
                best_session
                if best_ticks > 0
                else (all_sessions[0] if all_sessions else "default")
            )
        else:
            session_key = requested_session
        host = self._p._host(session_key)
        comp = host.kernel.computation
        logger.info(
            f"Sylanne WebUI state: session={session_key}, tick={comp._tick_count}, route={comp._last_route}"
        )

        # Emotion from Void-Scar Engine
        _EMOTION_DEFAULTS = {
            "warmth": 0.0,
            "arousal": 0.0,
            "valence": 0.0,
            "tension": 0.0,
            "curiosity": 0.0,
            "repair_pressure": 0.0,
            "expression_drive": 0.0,
            "boundary_firmness": 0.0,
            "coherence": 1.0,
        }
        emotion = {**_EMOTION_DEFAULTS, **comp.engine.observe()}

        # Gate stats
        gate_dict = comp.gate.to_dict()
        history = gate_dict.get("history", [])
        gate_info = {
            "precision": round(gate_dict.get("precision", 0.0), 4),
            "mean_surprise": round(gate_dict.get("mean_surprise", 0.0), 4),
            "history_len": gate_dict.get("history_len", 0),
            "history": history[-60:] if isinstance(history, list) else [],
        }

        # Route stats
        route_stats = {"fast": 0, "normal": 0, "full": 0, "skip": 0}
        if isinstance(history, list):
            for entry in history:
                r = entry.get("route", "fast") if isinstance(entry, dict) else "fast"
                if r in route_stats:
                    route_stats[r] += 1

        # Void-Scar state as memory equivalent
        engine_diag = comp.engine.diagnostics()
        _void_info = engine_diag.get("void", {})
        _mem_info = {
            "size": int(emotion.get("active_voids", 0)),
            "connectivity": comp.engine._coherence,
            "holes_count": int(emotion.get("active_voids", 0)),
            "ghost_count": int(emotion.get("ghost_count", 0)),
        }
        comp_result = getattr(host.kernel, "_last_computation_result", None) or {}
        layers = comp_result.get("layers", {})
        if not isinstance(layers, dict):
            layers = {}
        recalled_items = comp_result.get("recalled", [])
        _recent_recall = [
            str(r.get("text", ""))[:60] for r in recalled_items if isinstance(r, dict)
        ]

        # Boundary
        boundary_dict = comp.boundary.to_dict()
        boundary_info = {
            "integrity": round(boundary_dict.get("integrity", 1.0), 4),
            "entropy": round(boundary_dict.get("entropy", 0.0), 4),
            "stability": round(boundary_dict.get("stability", 1.0), 4),
            "phase_transitions": boundary_dict.get("phase_transitions", 0),
        }

        # Expression
        expr_state = comp.expression.state()
        expr_info = {
            "pressure": round(expr_state.get("pressure", 0.0), 4),
            "threshold": round(expr_state.get("threshold", 0.6), 4),
            "ratio": round(
                expr_state.get("pressure", 0.0)
                / max(0.01, expr_state.get("threshold", 0.6)),
                4,
            ),
            "mode": expr_state.get("mode", "silent"),
            "count": expr_state.get("count", 0),
        }

        # Timing (convert ns to ms for WebUI display)
        timing_raw = comp.timing_stats()
        timing: dict[str, Any] = {}
        total_ms = 0.0
        for layer_name, layer_stats in timing_raw.items():
            ms_val = round(layer_stats.get("p50_ns", 0.0) / 1_000_000, 3)
            timing[f"{layer_name}_ms"] = ms_val
            total_ms += ms_val
        timing["total_ms"] = round(total_ms, 3)

        # Ensure L1_HDC layer always has sample_bits for frontend visualization
        sample_bits = comp.last_hdc_sample if hasattr(comp, "last_hdc_sample") else []
        if "L1_HDC" not in layers:
            layers["L1_HDC"] = {
                "vector_dim": 2048,
                "density": sum(sample_bits) / max(len(sample_bits), 1)
                if sample_bits
                else 0.0,
                "sample_bits": sample_bits,
            }
        elif "sample_bits" not in layers["L1_HDC"]:
            layers["L1_HDC"]["sample_bits"] = sample_bits
            layers["L1_HDC"].setdefault("vector_dim", 2048)
            layers["L1_HDC"].setdefault(
                "density",
                sum(sample_bits) / max(len(sample_bits), 1) if sample_bits else 0.0,
            )

        # Feedback (from SSM diagnostics or computation diagnostics)
        comp_diag = comp.diagnostics()
        feedback_raw = comp_diag.get("feedback", {})
        if not feedback_raw:
            # Try to derive from body diagnostics
            surface = host.kernel.surface()
            diag = surface.get("diagnostics", {})
            feedback_raw = diag.get("feedback", {})
        feedback = {
            "accepted": int(feedback_raw.get("accepted", 0)),
            "ignored": int(feedback_raw.get("ignored", 0)),
            "rejected": int(feedback_raw.get("rejected", 0)),
        }
        spine_info = {
            "surprise": round(
                float(comp_result.get("surprise", gate_info["mean_surprise"]) or 0.0), 4
            ),
            "route": str(comp_result.get("route", "")),
            "last_text": str(comp_result.get("text", ""))[:120],
            "sheaf": comp_result.get("sheaf", {}),
            "hgt_decision": comp_result.get("hgt_decision", []),
            "boundary": boundary_info,
            "expression": expr_info,
            "layers": layers,
        }
        personality = (
            host.kernel._personality() if hasattr(host.kernel, "_personality") else {}
        )
        persona_info = {
            "profile": self._p._persona_profile(None),
            "traits": personality.get(
                "traits", personality if isinstance(personality, dict) else {}
            ),
            "voice": personality.get("voice", {})
            if isinstance(personality, dict)
            else {},
            "drift": personality.get("drift", {})
            if isinstance(personality, dict)
            else {},
        }

        return {
            "schema_version": "sylanne.webui.state.v1",
            "runtime": self._p._webui_runtime_info(),
            "current_session": session_key,
            "emotion": {k: round(v, 4) for k, v in emotion.items()},
            "gate": gate_info,
            "route_stats": route_stats,
            "boundary": boundary_info,
            "expression": expr_info,
            "timing": timing,
            "layers": layers,
            "spine": spine_info,
            "persona": persona_info,
            "theme": {"base": "#F3A7C8", "source": "emotion", "mode": "soft"},
            "feedback": feedback,
            "sessions": all_sessions,
            "life_simulation": self._p._life_simulator.to_dict(),
        }

    # ------------------------------------------------------------------
    # Settings handlers
    # ------------------------------------------------------------------

    async def settings_get_handler(self) -> dict[str, Any]:
        """Return current config values and schema for the settings panel."""
        schema = self._p._load_conf_schema()
        values = {}
        for key in schema:
            values[key] = self._p._config.get(key, schema[key].get("default"))
        return {
            "schema": schema,
            "values": values,
            "providers": await self.provider_items(),
        }

    async def provider_items(self) -> list[dict[str, Any]]:
        """Best-effort provider choices for WebUI datalist controls."""
        context = getattr(self._p, "context", None)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        def _add(provider: Any, provider_type: str = "") -> None:
            config = getattr(provider, "provider_config", None)
            if not isinstance(config, dict):
                config = {}
            provider_id = str(
                config.get("id")
                or config.get("provider_id")
                or getattr(provider, "provider_id", "")
                or getattr(provider, "id", "")
                or "",
            ).strip()
            if not provider_id or provider_id in seen:
                return
            seen.add(provider_id)
            items.append(
                {
                    "id": provider_id,
                    "name": str(
                        config.get("name")
                        or config.get("display_name")
                        or getattr(provider, "name", "")
                        or provider_id
                    ),
                    "type": str(
                        provider_type
                        or config.get("provider_type")
                        or getattr(provider, "provider_type", "")
                        or ""
                    ),
                }
            )

        for method_name, provider_type in (
            ("get_all_providers", "llm"),
            ("get_all_llm_providers", "llm"),
            ("get_all_embedding_providers", "embedding"),
        ):
            getter = getattr(context, method_name, None)
            if not callable(getter):
                continue
            try:
                providers = getter()
                if hasattr(providers, "__await__"):
                    providers = await providers
            except Exception:
                continue
            iterable = (
                providers.values() if isinstance(providers, dict) else (providers or [])
            )
            for provider in iterable:
                _add(provider, provider_type)
        return items

    async def settings_post_handler(self) -> dict[str, Any]:
        """Update config values from the settings panel."""
        from quart import request as quart_request

        body = await quart_request.get_json(silent=True) or {}
        schema = self._p._load_conf_schema()
        updated: list[str] = []
        for key, value in body.items():
            if key not in schema:
                continue
            meta = schema[key]
            # Type coercion
            if meta.get("type") == "bool":
                value = bool(value)
            elif meta.get("type") == "int":
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    continue
            elif meta.get("type") == "float":
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    continue
            else:
                value = str(value)
            self._p._config[key] = value
            updated.append(key)
        # Persist if possible
        config = self._p.config if hasattr(self._p, "config") else self._p._config
        if isinstance(config, dict):
            for key in updated:
                config[key] = self._p._config[key]
        if hasattr(config, "save_config"):
            config.save_config()
        self._p._start_webui_if_enabled()
        return {"ok": True, "updated": updated}

    # ------------------------------------------------------------------
    # Computation logs
    # ------------------------------------------------------------------

    async def computation_logs_handler(self) -> dict[str, Any]:
        """Return recent computation log entries for WebUI real-time display."""
        from quart import request as quart_request

        try:
            limit = max(1, min(200, int(quart_request.args.get("limit", "50"))))
        except (TypeError, ValueError):
            limit = 50
        requested_session = str(quart_request.args.get("session") or "").strip()
        logs = list(self._p._computation_logs)
        if requested_session:
            logs = [
                entry
                for entry in logs
                if str(entry.get("session", "")) == requested_session
            ]
        entries = logs[-limit:]
        return {
            "logs": entries,
            "total": len(self._p._computation_logs),
            "total_for_session": len(logs),
            "session": requested_session or "",
        }

    # ------------------------------------------------------------------
    # Memory pools
    # ------------------------------------------------------------------

    async def memory_pools_handler(self) -> dict[str, Any]:
        """Return hot and long-term Sylanne memory pools for the WebUI."""
        from quart import request as quart_request

        def _bounded_limit(raw: Any) -> int:
            try:
                return max(1, min(100, int(raw)))
            except (TypeError, ValueError):
                return 50

        def _temperature(record_data: dict[str, Any]) -> float:
            signature = record_data.get("emotional_signature") or {}
            if not isinstance(signature, dict):
                return 0.5
            arousal = abs(
                float(signature.get("arousal", signature.get("tension", 0.35)) or 0.35)
            )
            warmth = abs(
                float(signature.get("warmth", signature.get("valence", 0.45)) or 0.45)
            )
            return round(max(0.0, min(1.0, (arousal + warmth) / 2.0)), 4)

        def _weight(record_data: dict[str, Any]) -> float:
            depth = float(record_data.get("depth", 0.0) or 0.0)
            confidence = float(record_data.get("confidence", 0.35) or 0.35)
            recall = min(1.0, float(record_data.get("recall_count", 0) or 0) / 5.0)
            evidence = min(1.0, float(record_data.get("evidence_count", 1) or 1) / 4.0)
            interference = float(record_data.get("interference", 0.0) or 0.0)
            value = (
                depth * 0.45
                + confidence * 0.25
                + recall * 0.20
                + evidence * 0.10
                - interference * 0.15
            )
            return round(max(0.0, min(1.0, value)), 4)

        def _payload(record: Any) -> dict[str, Any]:
            data = (
                record.to_dict() if hasattr(record, "to_dict") else dict(record or {})
            )
            data["weight"] = _weight(data)
            data["temperature"] = _temperature(data)
            data["has_embedding"] = bool(
                data.get("embedding")
                or data.get("semantic_embedding")
                or data.get("embedding_provider_id")
            )
            data.pop("embedding", None)
            data.pop("semantic_embedding", None)
            return data

        def _has_memory_content(state: Any) -> bool:
            if state is None:
                return False
            if (
                hasattr(state, "_l1")
                or hasattr(state, "_l2")
                or hasattr(state, "_l3_nodes")
            ):
                return bool(
                    list(getattr(state, "_l1", []) or [])
                    or list(getattr(state, "_l2", []) or [])
                    or dict(getattr(state, "_l3_nodes", {}) or {})
                    or list(getattr(state, "_l3_edges", []) or [])
                )
            return bool(list(getattr(state, "records", []) or []))

        limit = _bounded_limit(quart_request.args.get("limit", "50"))
        session_key = str(quart_request.args.get("session") or "").strip()
        all_sessions = self._p._known_webui_sessions(session_key)
        overview_requested = not session_key or session_key == "default"
        if session_key and session_key not in all_sessions:
            all_sessions.append(session_key)
        if not session_key or (
            session_key not in all_sessions and session_key != "default"
        ):
            session_key = all_sessions[0] if all_sessions else "default"
        source_sessions = (
            [item for item in all_sessions if item]
            if overview_requested
            else [session_key]
        )
        if not source_sessions:
            source_sessions = [session_key or "default"]

        state = await self._p._load_sylanne_memory_state(session_key)

        # Fallback to the live 3-layer MemorySystem if KV state is unavailable
        if state is None:
            state = self._p._memory_system_for_session(session_key)

        def _memory_item_payload(item: Any) -> dict[str, Any]:
            data = item.to_dict() if hasattr(item, "to_dict") else dict(item or {})
            data["weight"] = round(
                max(0.0, min(1.0, float(data.get("weight", 0.0) or 0.0))), 4
            )
            data["temperature"] = round(
                max(0.0, min(1.0, float(data.get("temperature", 0.5) or 0.5))), 4
            )
            data["has_embedding"] = bool(
                data.get("embedding")
                or data.get("semantic_embedding")
                or data.get("embedding_provider_id")
            )
            data.pop("embedding", None)
            data.pop("semantic_embedding", None)
            return data

        def _graph_node_payload(node: Any) -> dict[str, Any]:
            data = node.to_dict() if hasattr(node, "to_dict") else dict(node or {})
            clarity = float(data.get("clarity", data.get("weight", 0.0)) or 0.0)
            emotion_weight = float(
                data.get("emotion_weight", data.get("temperature", 0.0)) or 0.0
            )
            data["summary"] = data.get(
                "label", data.get("summary", data.get("text", ""))
            )
            data["text"] = (
                data.get("text")
                or f"{data.get('type', 'node')} / {data.get('temporal_type', 'episodic')}"
            )
            data["weight"] = round(max(0.0, min(1.0, clarity)), 4)
            data["temperature"] = round(
                max(0.0, min(1.0, (emotion_weight + 1.0) / 2.0)), 4
            )
            data["has_embedding"] = False
            return data

        # Duplicated in webui_server.py for standalone mode
        def _legacy_trace_payload(trace: Any, source_session: str) -> dict[str, Any]:
            data = (
                dict(trace or {})
                if isinstance(trace, dict)
                else {"text": str(trace or "")}
            )
            weight = float(data.get("weight", data.get("depth", 0.35)) or 0.35)
            temperature = float(data.get("temperature", data.get("warmth", 0.5)) or 0.5)
            data["session"] = source_session
            data["source"] = data.get("source") or "body.memory.traces"
            data["weight"] = round(max(0.0, min(1.0, weight)), 4)
            data["temperature"] = round(max(0.0, min(1.0, temperature)), 4)
            data["created_at"] = float(
                data.get("created_at", data.get("updated_at", 0.0)) or 0.0
            )
            data["has_embedding"] = bool(
                data.get("embedding")
                or data.get("semantic_embedding")
                or data.get("embedding_provider_id")
            )
            data.pop("embedding", None)
            data.pop("semantic_embedding", None)
            return data

        async def _state_for_display(source_session: str) -> Any:
            loaded = await self._p._load_sylanne_memory_state(source_session)
            if loaded is not None:
                return loaded
            return self._p._memory_system_for_session(source_session)

        # Duplicated in webui_server.py for standalone mode
        def _body_traces_for_session(source_session: str) -> list[dict[str, Any]]:
            traces: list[dict[str, Any]] = []
            try:
                host = self._p._host(source_session)
                raw_traces = host.kernel.body.memory.get("traces", [])
            except Exception:
                raw_traces = []
            for trace in list(raw_traces or []):
                traces.append(_legacy_trace_payload(trace, source_session))
            return traces

        l1_items: list[dict[str, Any]] = []
        l2_items: list[dict[str, Any]] = []
        l3_nodes: list[dict[str, Any]] = []
        l3_edges: list[dict[str, Any]] = []
        raw_l1_count = 0
        raw_l2_count = 0
        raw_l3_node_count = 0
        raw_l3_edge_count = 0
        legacy_hot: list[dict[str, Any]] = []
        legacy_warm: list[dict[str, Any]] = []

        for source_session in source_sessions:
            source_state = await _state_for_display(source_session)
            if source_state is not None and (
                hasattr(source_state, "_l1")
                or hasattr(source_state, "_l2")
                or hasattr(source_state, "_l3_nodes")
            ):
                source_l1 = [
                    _memory_item_payload(item)
                    for item in list(getattr(source_state, "_l1", []) or [])
                ]
                source_l2 = [
                    _memory_item_payload(item)
                    for item in list(getattr(source_state, "_l2", []) or [])
                ]
                source_l3_nodes_raw = getattr(source_state, "_l3_nodes", {}) or {}
                source_l3_edges_raw = getattr(source_state, "_l3_edges", []) or []
                for item in source_l1 + source_l2:
                    item.setdefault("session", source_session)
                source_l3_nodes = [
                    _graph_node_payload(node)
                    for node in list(source_l3_nodes_raw.values())
                ]
                for node in source_l3_nodes:
                    node.setdefault("session", source_session)
                source_l3_edges = [
                    edge.to_dict() if hasattr(edge, "to_dict") else dict(edge or {})
                    for edge in list(source_l3_edges_raw)
                ]
                for edge in source_l3_edges:
                    edge.setdefault("session", source_session)
                l1_items.extend(source_l1)
                l2_items.extend(source_l2)
                l3_nodes.extend(source_l3_nodes)
                l3_edges.extend(source_l3_edges)
                raw_l1_count += len(getattr(source_state, "_l1", []) or [])
                raw_l2_count += len(getattr(source_state, "_l2", []) or [])
                raw_l3_node_count += len(source_l3_nodes_raw)
                raw_l3_edge_count += len(source_l3_edges_raw)
                if _has_memory_content(source_state):
                    continue

            traces = _body_traces_for_session(source_session)
            legacy_hot.extend(traces)
            legacy_warm.extend(
                item for item in traces if float(item.get("weight", 0.0) or 0.0) >= 0.5
            )

        if l1_items or l2_items or l3_nodes or legacy_hot:
            if legacy_hot:
                l1_items.extend(legacy_hot)
                l2_items.extend(legacy_warm)
                raw_l1_count += len(legacy_hot)
                raw_l2_count += len(legacy_warm)
            l1_items = sorted(
                l1_items,
                key=lambda item: float(item.get("created_at", 0.0) or 0.0),
                reverse=True,
            )[:limit]
            l2_items = sorted(
                l2_items,
                key=lambda item: (
                    float(item.get("weight", 0.0) or 0.0),
                    float(item.get("created_at", 0.0) or 0.0),
                ),
                reverse=True,
            )[:limit]
            l3_nodes = sorted(
                l3_nodes,
                key=lambda item: float(item.get("weight", 0.0) or 0.0),
                reverse=True,
            )[:limit]
            l3_edges = l3_edges[:limit]
            records = l1_items + l2_items + l3_nodes
            total = len(records)
            summary = {
                "total": total,
                "l1_count": raw_l1_count,
                "l2_count": raw_l2_count,
                "l3_node_count": raw_l3_node_count,
                "l3_edge_count": raw_l3_edge_count,
                "legacy_trace_count": len(legacy_hot),
                "embedded": sum(
                    1 for item in l1_items + l2_items if item.get("has_embedding")
                ),
                "avg_weight": round(
                    sum(float(item.get("weight", 0.0) or 0.0) for item in records)
                    / total,
                    4,
                )
                if total
                else 0.0,
                "avg_temperature": round(
                    sum(float(item.get("temperature", 0.0) or 0.0) for item in records)
                    / total,
                    4,
                )
                if total
                else 0.5,
            }
            return {
                "schema_version": "sylanne.webui.memory.v1",
                "architecture": "sylanne_alpha.memory_system.three_layer",
                "session": "default" if overview_requested else session_key,
                "mode": "overview" if overview_requested else "session",
                "sessions": source_sessions,
                "layers": {
                    "l1_hot": {
                        "label": "L1 Hot Pool",
                        "count": summary["l1_count"],
                        "capacity": 50,
                        "items": l1_items,
                    },
                    "l2_warm": {
                        "label": "L2 Warm Pool",
                        "count": summary["l2_count"],
                        "items": l2_items,
                    },
                    "l3_cold": {
                        "label": "L3 Cold Graph",
                        "count": summary["l3_node_count"],
                        "edge_count": summary["l3_edge_count"],
                        "nodes": l3_nodes,
                        "edges": l3_edges,
                    },
                },
                "hot": l1_items,
                "warm": l2_items,
                "cold": l3_nodes,
                "summary": summary,
            }

        records = [
            _payload(record) for record in list(getattr(state, "records", []) or [])
        ]
        hot = sorted(
            records,
            key=lambda item: float(item.get("created_at", 0.0) or 0.0),
            reverse=True,
        )[:limit]
        warm = sorted(
            (
                item
                for item in records
                if float(item.get("weight", 0.0) or 0.0) >= 0.5
                or int(item.get("recall_count", 0) or 0) > 0
            ),
            key=lambda item: (
                float(item.get("weight", 0.0) or 0.0),
                float(item.get("updated_at", 0.0) or 0.0),
            ),
            reverse=True,
        )[:limit]
        total = len(records)
        summary = {
            "total": total,
            "l1_count": len(hot),
            "l2_count": len(warm),
            "l3_node_count": 0,
            "l3_edge_count": 0,
            "embedded": sum(1 for item in records if item.get("has_embedding")),
            "avg_weight": round(
                sum(float(item.get("weight", 0.0) or 0.0) for item in records) / total,
                4,
            )
            if total
            else 0.0,
            "avg_temperature": round(
                sum(float(item.get("temperature", 0.0) or 0.0) for item in records)
                / total,
                4,
            )
            if total
            else 0.5,
        }
        return {
            "schema_version": "sylanne.webui.memory.v1",
            "architecture": "legacy.sylanne_memory_state.compat",
            "session": session_key,
            "layers": {
                "l1_hot": {
                    "label": "L1 Hot Pool",
                    "count": len(hot),
                    "capacity": 50,
                    "items": hot,
                },
                "l2_warm": {"label": "L2 Warm Pool", "count": len(warm), "items": warm},
                "l3_cold": {
                    "label": "L3 Cold Graph",
                    "count": 0,
                    "edge_count": 0,
                    "nodes": [],
                    "edges": [],
                },
            },
            "hot": hot,
            "warm": warm,
            "cold": [],
            "long_term": warm,
            "summary": summary,
        }

    # ------------------------------------------------------------------
    # Memory meltdown
    # ------------------------------------------------------------------

    async def memory_meltdown_handler(self) -> dict[str, Any]:
        """Clear all memory pools for a session. Supports both server nonce and client token verification."""
        from quart import request as quart_request

        try:
            body = await quart_request.get_json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            return {"ok": False, "error": "invalid_body"}
        session = str(body.get("session", "")).strip()
        token = str(body.get("token", "")).strip()
        # Try server-side nonce first
        server_nonce = getattr(self._p, "_meltdown_nonces", {}).get(session, "")
        if server_nonce and token == server_nonce:
            self._p._meltdown_nonces.pop(session, None)
        else:
            # Fallback: client-side token verification (frontend generates + sends both)
            expected_token = str(body.get("expected_token", "")).strip()
            if not token or not expected_token or token != expected_token:
                return {"ok": False, "error": "token_mismatch"}
        # Clear memory for the session
        mem_sys = (
            self._p._memory_system_for_session(session)
            if hasattr(self._p, "_memory_system_for_session")
            else getattr(self._p, "_memory_system", None)
        )
        if mem_sys:
            mem_sys._l1.clear()
            mem_sys._l2.clear()
            mem_sys._l3_nodes.clear()
            mem_sys._l3_edges.clear()
            mem_sys._tick = 0
        # Also clear legacy body traces
        hosts = getattr(self._p, "_hosts", {}) or {}
        if session in hosts:
            hosts[session].kernel.body.memory["traces"] = []
            hosts[session].kernel.body.memory.pop("_memory_system", None)
        logger.info(f"Sylanne MEMORY MELTDOWN: session={session} — all memory cleared")
        # Set amnesia flag so next LLM response expresses memory loss
        if not hasattr(self._p, "_amnesia_sessions"):
            self._p._amnesia_sessions: set[str] = set()
        self._p._amnesia_sessions.add(session)
        return {"ok": True, "session": session, "cleared": True}

    def generate_meltdown_nonce(self, session: str) -> str:
        """Generate a one-time nonce for memory meltdown confirmation."""
        nonce = secrets.token_hex(16)
        self._p._meltdown_nonces[session] = nonce
        return nonce

    # ------------------------------------------------------------------
    # Probe handler
    # ------------------------------------------------------------------

    async def probe_handler(self) -> dict[str, Any]:
        """Probe the standalone WebUI listener from inside the plugin process."""
        import urllib.error
        import urllib.request

        enabled = self._p._cfg_bool("sylanne_webui_enabled", False)
        host = str(self._p._cfg("sylanne_webui_host", "0.0.0.0") or "0.0.0.0")
        port = self._p._cfg_int("sylanne_webui_port", 2718)
        expected_runtime = self._p._webui_runtime_info()
        stopped: list[str] = []
        module_count_before = len(self._p._iter_loaded_webui_server_modules())
        if enabled:
            stopped = await self._p._stop_stale_webui_server_modules(
                include_current=True
            )
            if stopped:
                self._p.logger.info(
                    f"Sylanne WebUI probe stopped stale listener modules: {stopped}"
                )
            self._p._start_webui_if_enabled()
            await asyncio.sleep(0.2)
        module_count_after = len(self._p._iter_loaded_webui_server_modules())

        local_url = f"http://127.0.0.1:{port}/api/state"

        def _probe_local() -> dict[str, Any]:
            probe: dict[str, Any] = {
                "ok": False,
                "url": local_url,
                "status": 0,
                "schema_version": "",
                "runtime": {},
                "runtime_match": False,
                "error": "",
            }
            try:
                with urllib.request.urlopen(local_url, timeout=2.0) as response:
                    raw = response.read().decode("utf-8", errors="replace")
                    payload = json.loads(raw)
                    runtime = (
                        payload.get("runtime", {}) if isinstance(payload, dict) else {}
                    )
                    if not isinstance(runtime, dict):
                        runtime = {}
                    runtime_match = (
                        str(runtime.get("runtime_id", ""))
                        == expected_runtime["runtime_id"]
                    )
                    probe.update(
                        {
                            "ok": response.status == 200
                            and payload.get("schema_version")
                            == "sylanne.webui.state.v1"
                            and runtime_match,
                            "status": response.status,
                            "schema_version": str(payload.get("schema_version", "")),
                            "runtime": runtime,
                            "runtime_match": runtime_match,
                        }
                    )
            except urllib.error.HTTPError as exc:
                probe.update({"status": exc.code, "error": str(exc)})
            except Exception as exc:
                probe["error"] = f"{type(exc).__name__}: {exc}"
            return probe

        probe = await asyncio.to_thread(_probe_local)

        return {
            "schema_version": "sylanne.webui.probe.v1",
            "enabled": enabled,
            "host": host,
            "port": port,
            "expected_runtime": expected_runtime,
            "local": probe,
            "takeover": {
                "module_count_before": module_count_before,
                "module_count_after": module_count_after,
                "stopped": stopped,
            },
            "public_hint": f"http://<server-ip>:{port}/",
        }

    # ------------------------------------------------------------------
    # Logo & dashboard
    # ------------------------------------------------------------------

    async def logo_handler(self) -> Any:
        """Serve the plugin logo.png with correct Content-Type."""
        from quart import Response

        logo_path = Path(self._plugin_dir) / "logo.png"
        if not logo_path.exists():
            return Response("Not Found", status=404)
        data = logo_path.read_bytes()
        return Response(data, content_type="image/png")

    async def dashboard_handler(self) -> Any:
        """Serve the WebUI dashboard HTML via AstrBot's own web server."""
        from quart import Response

        dashboard_path = Path(self._plugin_dir) / "pages" / "dashboard" / "index.html"
        if not dashboard_path.exists():
            return Response("Dashboard not found", status=404)
        html = dashboard_path.read_text(encoding="utf-8")
        return Response(html, content_type="text/html; charset=utf-8")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def _plugin_dir(self) -> str:
        """Resolve plugin directory from the plugin instance or module-level constant."""
        import main as _main_mod

        return getattr(_main_mod, "_PLUGIN_DIR", ".")
