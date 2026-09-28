"""Windows companion: Civ VI Lua.log -> OpenAI -> focused in-game panel."""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from advisor import ask_openai, build_payload
from state import log_candidates, read_snapshot
from windows_delivery import WindowsDelivery

CHAT_MARKER = "CIV6AI_CHAT_V1|"
FRAME_PREFIX = "CIV6AI_REPLY|"
CHUNK_SIZE = 380  # safe for the game's single-line EditBox


class Tail:
    def __init__(self):
        self.path: Path | None = None
        self.offset = 0
        self.partial = b""

    def read(self) -> list[str]:
        candidates = [p for p in log_candidates() if p.is_file()]
        if not candidates:
            return []
        path = max(candidates, key=lambda p: p.stat().st_mtime)
        if path != self.path:
            self.path, self.offset, self.partial = path, path.stat().st_size, b""
            print(f"正在監聽：{path}（請在遊戲內重新提問）")
            return []
        size = path.stat().st_size
        if size < self.offset:
            self.offset, self.partial = 0, b""
        if size == self.offset:
            return []
        with path.open("rb") as handle:
            handle.seek(self.offset)
            data = self.partial + handle.read()
            self.offset = handle.tell()
        parts = data.split(b"\n")
        self.partial = parts.pop()
        return [line.decode("utf-8-sig", errors="replace") for line in parts]


class Companion:
    def __init__(self, delivery, tail=None, executor=None):
        self.delivery = delivery
        self.tail = tail or Tail()
        self.executor = executor or ThreadPoolExecutor(max_workers=1)
        self.requests: dict[str, dict] = {}
        self.history: list[dict] = []
        self.active: str | None = None

    def process_line(self, line: str):
        position = line.find(CHAT_MARKER)
        if position < 0:
            return
        fields = line[position + len(CHAT_MARKER):].split("|", 2)
        if len(fields) != 3:
            return
        token, action, body = fields
        if not token.isdigit():
            return
        if action == "ASK":
            try:
                question = json.loads(body).get("question", "")
            except (ValueError, AttributeError):
                return
            if not isinstance(question, str) or not 0 < len(question) <= 1000:
                return
            if token in self.requests:
                return
            snapshot = read_snapshot()
            payload = build_payload(question, snapshot, self.history[-8:])
            self.requests[token] = {"future": self.executor.submit(ask_openai, payload),
                                    "question": question, "ready_at": 0, "next": 0,
                                    "sent_at": 0, "chunks": None}
            print(f"收到遊戲內問題 #{token}，正在向 OpenAI 詢問…")
        elif action == "READY" and token in self.requests:
            self.requests[token]["ready_at"] = time.monotonic()
            self.requests[token]["next"] = 0
            self.requests[token]["sent_at"] = 0
            self.active = token
        elif action == "ACK" and token == self.active:
            request = self.requests[token]
            if request["sent_at"]:
                try:
                    sequence = int(body)
                except ValueError:
                    return
                if sequence == request["next"] + 1:
                    request["next"] += 1
                    request["sent_at"] = 0
                    request["ready_at"] = time.monotonic()
                    if request["next"] == len(request["chunks"]):
                        self.delivery.restore_text()
                        self.history.extend([{"role": "user", "content": request["question"]},
                                             {"role": "assistant", "content": request["answer"]}])
                        print(f"遊戲內回答 #{token} 已接收。")
                        del self.requests[token]
                        self.active = None

    def tick(self):
        for line in self.tail.read():
            self.process_line(line)
        for token, request in list(self.requests.items()):
            if request["chunks"] is None and request["future"].done():
                try:
                    request["answer"] = request["future"].result()
                except Exception as exc:
                    request["answer"] = "助手暫時無法回答：" + str(exc)
                answer = request["answer"].replace("\r", " ").replace("\n", "　")
                request["chunks"] = [answer[n:n + CHUNK_SIZE] for n in range(0, len(answer), CHUNK_SIZE)] or ["（沒有內容）"]
                print(f"回答 #{token} 已產生；請在遊戲內按「接收回答」。")
        if not self.active:
            return
        token = self.active
        request = self.requests[token]
        if not request["future"].done():
            return
        if request["chunks"] is None:
            return
        now = time.monotonic()
        if request["sent_at"]:
            if now - request["sent_at"] > 3:
                print("遊戲未確認收到回答；請再按「接收回答」。")
                self.delivery.restore_text()
                request["ready_at"] = 0
                request["sent_at"] = 0
                self.active = None
            return
        if now - request["ready_at"] > 3:
            self.active = None
            return
        sequence = request["next"] + 1
        frame = f"{FRAME_PREFIX}{token}|{sequence}|{len(request['chunks'])}|{request['chunks'][sequence-1]}"
        if self.delivery.paste(frame):
            request["sent_at"] = now


def main():
    if os.name != "nt":
        raise SystemExit("請在執行 Civ VI 的 Windows 電腦上啟動此程式。")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("請先在此終端機設定 OPENAI_API_KEY。")
    companion = Companion(WindowsDelivery())
    print("文明 VI 助手已啟動：在遊戲內輸入問題並按「詢問」。回答完成後按「接收回答」。")
    try:
        while True:
            companion.tick()
            time.sleep(0.12)
    except KeyboardInterrupt:
        companion.delivery.restore_text()
        companion.executor.shutdown(wait=False, cancel_futures=True)
        print("已停止。")


if __name__ == "__main__":
    main()
