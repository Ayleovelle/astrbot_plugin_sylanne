"""Source contracts for the AstrBot 4.26 Web API migration."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "main.py"
ROUTES_PATH = ROOT / "sylanne_alpha" / "webui_routes.py"


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _function(tree: ast.Module, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"function {name!r} not found")


def _call_name(call: ast.Call) -> str:
    node: ast.expr = call.func
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _imported_names(tree: ast.Module, module: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def _quart_imports(tree: ast.Module) -> list[str]:
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names if alias.name == "quart" or alias.name.startswith("quart."))
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "quart" or node.module.startswith("quart."):
                imports.append(node.module)
    return imports


def _awaits_request_json(fn: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    return any(
        isinstance(node, ast.Await)
        and isinstance(node.value, ast.Call)
        and _call_name(node.value) == "request.json"
        for node in ast.walk(fn)
    )


def _uses_request_query(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "request"
        and node.attr == "query"
        for node in ast.walk(tree)
    )


def _called_helpers(fn: ast.AsyncFunctionDef | ast.FunctionDef) -> set[str]:
    return {
        _call_name(node).rsplit(".", 1)[-1]
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
    }


def _decorator_names(fn: ast.AsyncFunctionDef | ast.FunctionDef) -> set[str]:
    names: set[str] = set()
    for decorator in fn.decorator_list:
        call = decorator if isinstance(decorator, ast.Call) else None
        target = call.func if call is not None else decorator
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(_call_name(ast.Call(func=target, args=[], keywords=[])))
    return names


def test_web_api_modules_do_not_import_quart() -> None:
    offenders = {
        path.relative_to(ROOT).as_posix(): _quart_imports(_tree(path))
        for path in (MAIN_PATH, ROUTES_PATH)
    }
    offenders = {path: imports for path, imports in offenders.items() if imports}
    assert offenders == {}, f"AstrBot 4.26 Web API must not import Quart: {offenders}"


def test_json_body_handlers_use_astrbot_web_request_json() -> None:
    handlers_by_path = {
        MAIN_PATH: ("_memory_settings_post_handler",),
        ROUTES_PATH: (
            "memory_settings_post_handler",
            "settings_post_handler",
            "memory_meltdown_handler",
            "memory_consolidate_handler",
            "life_controls_handler",
            "config_import_handler",
            "proactive_feedback_handler",
            "personality_import_handler",
        ),
    }

    failures: list[str] = []
    for path, handlers in handlers_by_path.items():
        tree = _tree(path)
        if "request" not in _imported_names(tree, "astrbot.api.web"):
            failures.append(f"{path.relative_to(ROOT)} does not import astrbot.api.web.request")
        for handler_name in handlers:
            if not _awaits_request_json(_function(tree, handler_name)):
                failures.append(f"{path.relative_to(ROOT)}::{handler_name} does not await request.json()")

    assert failures == [], "\n".join(failures)


def test_query_parameters_use_request_query_not_quart_args() -> None:
    tree = _tree(ROUTES_PATH)
    legacy_args = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "args"
    ]
    assert legacy_args == [], f"query handlers still use Quart request.args at lines {legacy_args}"
    assert _uses_request_query(tree), "query handlers must read astrbot.api.web.request.query"


def test_html_logo_and_dashboard_use_public_web_response_helpers() -> None:
    tree = _tree(ROUTES_PATH)
    imported = _imported_names(tree, "astrbot.api.web")
    public_helpers = {"error_response", "file_response", "stream_response"}

    failures: list[str] = []
    for handler_name in ("page_handler", "logo_handler", "dashboard_handler"):
        called = _called_helpers(_function(tree, handler_name))
        if not called & public_helpers:
            failures.append(f"{handler_name} calls no public astrbot.api.web response helper")
        if "Response" in called:
            failures.append(f"{handler_name} still constructs Quart Response directly")

    assert imported & public_helpers, "webui_routes must import public astrbot.api.web response helpers"
    assert failures == [], "\n".join(failures)


def test_using_llm_tool_hook_is_not_an_llm_function_tool() -> None:
    tree = _tree(MAIN_PATH)
    hook = _function(tree, "on_using_llm_tool")
    decorators = _decorator_names(hook)
    assert decorators == {"_optional_tool_use_filter"}

    resolver = _function(tree, "_optional_tool_use_filter")
    string_constants = {
        node.value
        for node in ast.walk(resolver)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "on_using_llm_tool" in string_constants
    assert "llm_tool" not in string_constants


def test_query_agent_state_tool_has_no_model_arguments_requiring_args_docstring() -> None:
    tree = _tree(MAIN_PATH)
    tool = _function(tree, "_llm_tool_query_agent_state")
    assert _decorator_names(tool) == {"_model_function_tool"}

    resolver = _function(tree, "_model_function_tool")
    assert any(
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "filter"
        and node.attr == "llm_tool"
        for node in ast.walk(resolver)
    )

    positional = [arg.arg for arg in (*tool.args.posonlyargs, *tool.args.args)]
    assert positional[:2] == ["self", "event"]
    assert positional[2:] == []
    assert tool.args.kwonlyargs == []
    assert tool.args.vararg is None
    assert tool.args.kwarg is None
    assert ast.get_docstring(tool), "the zero-argument tool should still have a user-facing description"
