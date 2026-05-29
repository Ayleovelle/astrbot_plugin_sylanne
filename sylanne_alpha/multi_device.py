"""Sylanne-Embodiment: 多端协作系统。

整合多实例协作协议和状态同步（LWW-CRDT）。
提供实例间消息传递和跨设备状态合并能力。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


# ======================================================================
# 多实例协作协议
# ======================================================================


@dataclass
class InstanceMessage:
    sender_id: str
    content: str
    personality_snapshot: dict
    timestamp: float


class MultiInstanceProtocol:
    def __init__(self, instance_id: str):
        self.instance_id = instance_id
        self._peers: dict[str, dict] = {}
        self._inbox: list[InstanceMessage] = []
        self._outbox: list[InstanceMessage] = []

    def register_peer(self, peer_id: str, personality: dict):
        self._peers[peer_id] = {"last_seen": time.time(), "personality": personality}

    def send_message(self, peer_id: str, content: str, personality: dict) -> bool:
        if peer_id not in self._peers:
            return False
        self._outbox.append(
            InstanceMessage(self.instance_id, content, personality, time.time())
        )
        return True

    def deliver_to_inbox(self, msg: InstanceMessage):
        self._inbox.append(msg)

    def receive_messages(self) -> list[InstanceMessage]:
        msgs = list(self._inbox)
        self._inbox.clear()
        return msgs

    def drain_outbox(self) -> list[InstanceMessage]:
        msgs = list(self._outbox)
        self._outbox.clear()
        return msgs

    def get_collaboration_mode(self) -> str:
        if not self._peers:
            return "solo"
        return "debate"

    def peer_count(self) -> int:
        return len(self._peers)


# ======================================================================
# 状态同步（LWW-CRDT）
# ======================================================================


@dataclass
class StateVector:
    data: dict = field(default_factory=dict)
    timestamps: dict = field(default_factory=dict)
    device_id: str = ""

    def set(self, key: str, value, device: str = ""):
        self.data[key] = value
        self.timestamps[key] = time.time()
        self.device_id = device or self.device_id

    def get(self, key: str, default=None):
        return self.data.get(key, default)


class SyncManager:
    def __init__(self, device_id: str = "default"):
        self._local: StateVector = StateVector(device_id=device_id)
        self._device_id = device_id

    def update_local(self, key: str, value):
        self._local.set(key, value, self._device_id)

    def merge(self, remote: StateVector) -> list[str]:
        overwritten = []
        for key, remote_ts in remote.timestamps.items():
            local_ts = self._local.timestamps.get(key, 0)
            if remote_ts > local_ts:
                self._local.data[key] = remote.data[key]
                self._local.timestamps[key] = remote_ts
                overwritten.append(key)
        return overwritten

    def get_state(self) -> StateVector:
        return self._local

    def has_conflicts(self, remote: StateVector) -> list[str]:
        conflicts = []
        for key in remote.timestamps:
            if key in self._local.timestamps:
                if abs(remote.timestamps[key] - self._local.timestamps[key]) < 1.0:
                    conflicts.append(key)
        return conflicts

    def to_dict(self) -> dict:
        return {
            "data": self._local.data,
            "timestamps": self._local.timestamps,
            "device": self._device_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SyncManager":
        sm = cls(data.get("device", "default"))
        sm._local.data = data.get("data", {})
        sm._local.timestamps = data.get("timestamps", {})
        return sm
