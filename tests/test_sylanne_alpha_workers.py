from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sylanne_alpha.workers import BackgroundQueue


class SylanneAlphaWorkerTests(unittest.TestCase):
    def test_background_queue_checkpoints_without_raw_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = BackgroundQueue(Path(tmp), session_key="room")
            queue.enqueue("fragment_compaction", {"text": "一段私密原文", "summary": "碎片摘要"})
            queue.checkpoint()
            restored = BackgroundQueue(Path(tmp), session_key="room")

        self.assertEqual(restored.pending_count(), 1)
        snapshot = restored.snapshot()
        self.assertEqual(snapshot["schema_version"], "sylanne.alpha.workers.v1")
        self.assertNotIn("一段私密原文", str(snapshot))
        self.assertEqual(snapshot["jobs"][0]["payload"]["summary"], "碎片摘要")

    def test_background_queue_respects_worker_cap_and_fifo(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = BackgroundQueue(Path(tmp), session_key="room", max_workers=2)
            queue.enqueue("a", {"summary": "1"})
            queue.enqueue("b", {"summary": "2"})
            queue.enqueue("c", {"summary": "3"})
            leased = queue.lease_ready()

        self.assertEqual([job["kind"] for job in leased], ["a", "b"])
        self.assertEqual(queue.pending_count(), 1)
        self.assertEqual(queue.inflight_count(), 2)


if __name__ == "__main__":
    unittest.main()
