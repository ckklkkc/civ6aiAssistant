import io
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen

import advisor
import server
from state import MARKER, read_snapshot


def sample():
    return {"status": "ok", "source": "civ6_ui_mod", "visibility": "currently_visible",
            "updated_at": "2026-09-28T12:00:00+00:00",
            "meta": {"kind": "meta", "turn": 27, "civilization": "CIVILIZATION_KOREA"},
            "cities": [{"kind": "city", "name": "首爾", "x": 3, "y": 4}],
            "units": [], "plots": [{"kind": "plot", "x": 4, "y": 4, "production": 2}]}


class StateTests(unittest.TestCase):
    def test_complete_snapshot_ignores_incomplete_later_export(self):
        items = [sample()["meta"], sample()["cities"][0], sample()["plots"][0]]
        lines = [f"[InGame] {MARKER}270001|BEGIN|3|{{}}"]
        lines += [f"[InGame] {MARKER}270001|ITEM|{n}|{json.dumps(item, ensure_ascii=False)}"
                  for n, item in enumerate(items, 1)]
        lines += [f"[InGame] {MARKER}270001|END|3|{{}}", f"[InGame] {MARKER}270002|BEGIN|1|{{}}"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Lua.log"
            path.write_text("\n".join(lines), encoding="utf-8")
            result = read_snapshot([path])
            self.assertEqual(result["meta"]["turn"], 27)
            self.assertEqual(result["cities"][0]["name"], "首爾")
            self.assertEqual(len(result["plots"]), 1)
            path.write_text("\n".join(lines[:-2]), encoding="utf-8")
            self.assertEqual(read_snapshot([path])["status"], "no_snapshot")


class AdvisorTests(unittest.TestCase):
    def test_payload_contains_game_and_image_but_does_not_store(self):
        payload = advisor.build_payload("學院蓋哪？", sample(), [], "abc")
        self.assertFalse(payload["store"])
        self.assertIn("首爾", payload["input"][-1]["content"][0]["text"])
        self.assertEqual(payload["input"][-1]["content"][1]["type"], "input_image")

    def test_openai_http_response(self):
        class FakeResponse(io.BytesIO):
            pass
        def fake_open(request, timeout):
            self.assertEqual(request.get_method(), "POST")
            self.assertEqual(timeout, 90)
            self.assertEqual(json.loads(request.data)["model"], "gpt-5-mini")
            return FakeResponse(json.dumps({"output": [{"type": "message", "content": [
                {"type": "output_text", "text": "先建學院"}]}]}).encode())
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-placeholder", "OPENAI_MODEL": "gpt-5-mini"}):
            self.assertEqual(advisor.ask_openai(advisor.build_payload("測試", sample(), []), fake_open), "先建學院")


class ServerTests(unittest.TestCase):
    def test_local_api_from_snapshot_to_answer(self):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{httpd.server_port}"
        try:
            with patch.object(server, "read_snapshot", return_value=sample()), patch.object(
                    server, "ask_openai", return_value="選擇 (4,4) 附近") as mocked:
                with urlopen(base + "/api/state") as response:
                    self.assertEqual(json.load(response)["meta"]["turn"], 27)
                body = json.dumps({"question": "下一步？", "history": []}).encode()
                request = Request(base + "/api/ask", data=body, method="POST", headers={"Content-Type": "application/json"})
                with urlopen(request) as response:
                    self.assertIn("(4,4)", json.load(response)["answer"])
                self.assertEqual(mocked.call_args.args[0]["input"][-1]["content"][0]["type"], "input_text")
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
