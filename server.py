"""Local-only Civ VI advisor. Run: python server.py"""
from __future__ import annotations

import base64
import binascii
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from advisor import ask_openai, build_payload
from state import read_snapshot

ROOT = Path(__file__).resolve().parent / "web"
PORT = int(os.environ.get("CIV6_ASSISTANT_PORT", "5001"))
STATIC = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
          "/style.css": ("style.css", "text/css")}


class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, code: int, data: bytes, content_type: str):
        self.send_response(code)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; connect-src 'self'")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, code: int, value: dict):
        self.send_bytes(code, json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json")

    def authorized_host(self) -> bool:
        return self.headers.get("Host", "").split(":")[0].lower() in ("localhost", "127.0.0.1")

    def do_GET(self):
        if not self.authorized_host():
            return self.send_json(403, {"error": "僅接受本機請求"})
        if self.path == "/api/state":
            snapshot = read_snapshot()
            return self.send_json(200, snapshot)
        if self.path == "/api/health":
            return self.send_json(200, {"ready": bool(os.environ.get("OPENAI_API_KEY")),
                                         "model": os.environ.get("OPENAI_MODEL", "gpt-5-mini")})
        if self.path not in STATIC:
            return self.send_json(404, {"error": "找不到頁面"})
        name, mime = STATIC[self.path]
        self.send_bytes(200, (ROOT / name).read_bytes(), mime)

    def do_POST(self):
        if not self.authorized_host() or self.path != "/api/ask":
            return self.send_json(403, {"error": "僅接受本機請求"})
        origin = self.headers.get("Origin")
        if origin and origin not in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"):
            return self.send_json(403, {"error": "來源不符"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 6_000_000:
                return self.send_json(413, {"error": "請求太大或為空"})
            body = json.loads(self.rfile.read(length))
            question = body.get("question")
            if not isinstance(question, str) or not question.strip() or len(question) > 4000:
                return self.send_json(400, {"error": "請輸入 1 至 4000 字的問題"})
            history = body.get("history", [])
            if not isinstance(history, list):
                return self.send_json(400, {"error": "對話紀錄格式錯誤"})
            image = body.get("image")
            if image is not None:
                if not isinstance(image, str) or len(image) > 5_000_000:
                    return self.send_json(400, {"error": "圖片過大"})
                raw = base64.b64decode(image, validate=True)
                if not raw.startswith(b"\x89PNG\r\n\x1a\n") or len(raw) > 3_750_000:
                    return self.send_json(400, {"error": "只接受 PNG 截圖，大小不超過 3.75 MB"})
            payload = build_payload(question.strip(), read_snapshot(), history, image)
            answer = ask_openai(payload)
            self.send_json(200, {"answer": answer})
        except (ValueError, binascii.Error, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": str(exc) if isinstance(exc, ValueError) else "資料格式錯誤"})
        except RuntimeError as exc:
            self.send_json(502, {"error": str(exc)})
        except Exception:
            self.send_json(500, {"error": "伺服器處理失敗；請檢查終端機輸出。"})
            raise


if __name__ == "__main__":
    address = ("127.0.0.1", PORT)
    print(f"Civ VI AI Assistant: http://{address[0]}:{address[1]}")
    ThreadingHTTPServer(address, Handler).serve_forever()
