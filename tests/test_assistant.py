import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import advisor
import bridge
from state import MARKER, read_snapshot


def sample():
    return {"status": "ok", "source": "civ6_ui_mod", "visibility": "currently_visible",
            "updated_at": "2026-09-28T12:00:00+00:00",
            "meta": {"kind": "meta", "turn": 27, "civilization": "CIVILIZATION_KOREA"},
            "cities": [{"kind": "city", "name": "首爾", "x": 3, "y": 4}],
            "units": [], "plots": [{"kind": "plot", "x": 4, "y": 4, "production": 2}]}


class StateTests(unittest.TestCase):
    def test_complete_snapshot_ignores_incomplete_tail(self):
        items = [sample()["meta"], sample()["cities"][0], sample()["plots"][0]]
        lines = [f"[InGame] {MARKER}270001|BEGIN|3|{{}}"]
        lines += [f"[InGame] {MARKER}270001|ITEM|{n}|{json.dumps(item, ensure_ascii=False)}"
                  for n, item in enumerate(items, 1)]
        lines += [f"[InGame] {MARKER}270001|END|3|{{}}", f"[InGame] {MARKER}270002|BEGIN|1|{{}}"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Lua.log"
            path.write_text("\n".join(lines), encoding="utf-8")
            self.assertEqual(read_snapshot([path])["cities"][0]["name"], "首爾")
            path.write_text("\n".join(lines[:-2]), encoding="utf-8")
            self.assertEqual(read_snapshot([path])["status"], "no_snapshot")


class AdvisorTests(unittest.TestCase):
    def test_payload_and_http_response(self):
        payload = advisor.build_payload("學院蓋哪？", sample(), [])
        self.assertFalse(payload["store"])
        self.assertIn("首爾", payload["input"][-1]["content"][0]["text"])

        def fake_open(request, timeout):
            self.assertEqual(request.get_method(), "POST")
            self.assertEqual(timeout, 90)
            return io.BytesIO(json.dumps({"output": [{"type": "message", "content": [
                {"type": "output_text", "text": "先建學院"}]}]}).encode())
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-only"}):
            self.assertEqual(advisor.ask_openai(payload, fake_open), "先建學院")


class BridgeTests(unittest.TestCase):
    def test_tailer_skips_old_requests_and_handles_partial_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'Lua.log'
            path.write_bytes(b'old request\n')
            tail = bridge.Tail()
            with patch.object(bridge, 'log_candidates', return_value=[path]):
                self.assertEqual(tail.read(), [])
                with path.open('ab') as output:
                    output.write(b'new re')
                self.assertEqual(tail.read(), [])
                with path.open('ab') as output:
                    output.write(b'quest\n')
                self.assertEqual(tail.read(), ['new request'])

    def test_in_game_question_and_acknowledged_multipage_answer(self):
        class FakeDelivery:
            def __init__(self):
                self.frames = []
                self.restored = False
            def paste(self, frame):
                self.frames.append(frame)
                return True
            def restore_text(self):
                self.restored = True

        class FakeTail:
            def read(self):
                return []

        class Immediate:
            def result(self):
                return "甲" * 500
            def done(self):
                return True

        class Executor:
            def submit(self, func, payload):
                self_payload.append(payload)
                return Immediate()

        self_payload = []
        delivery = FakeDelivery()
        companion = bridge.Companion(delivery, FakeTail(), Executor())
        with patch.object(bridge, "read_snapshot", return_value=sample()):
            companion.process_line('[InGame] CIV6AI_CHAT_V1|270001|ASK|{"question":"我該蓋哪？"}')
        self.assertEqual(self_payload[0]["input"][-1]["role"], "user")
        companion.tick()
        companion.process_line('[InGame] CIV6AI_CHAT_V1|270001|READY|{}')
        companion.tick()
        self.assertTrue(delivery.frames[0].startswith('CIV6AI_REPLY|270001|1|2|'))
        companion.process_line('[InGame] CIV6AI_CHAT_V1|270001|ACK|1')
        companion.tick()
        self.assertTrue(delivery.frames[1].startswith('CIV6AI_REPLY|270001|2|2|'))
        companion.process_line('[InGame] CIV6AI_CHAT_V1|270001|ACK|2')
        self.assertTrue(delivery.restored)
        self.assertEqual(len(companion.history), 2)


if __name__ == "__main__":
    unittest.main()
