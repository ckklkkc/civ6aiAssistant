# -*- coding: utf-8 -*-
import base64
import configparser
import io
import logging
import os
import time

import google.generativeai as genai
from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS
from PIL import ImageGrab

from save_context import Civ6ContextConfig, build_context, context_for_prompt
from mod_bridge import latest_snapshot, snapshot_for_prompt

app = Flask(__name__)
CORS(app)


class StreamLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.queue = []

    def emit(self, record):
        self.queue.append(self.format(record))


stream_handler = StreamLogHandler()
formatter = logging.Formatter('[%(asctime)s] %(message)s', '%H:%M:%S')
stream_handler.setFormatter(formatter)
app.logger.addHandler(stream_handler)
app.logger.setLevel(logging.INFO)

model = None
chat_session = None
system_prompt = ""
civ6_config = Civ6ContextConfig()
mod_log_path = ""


def load_config():
    config = configparser.ConfigParser()
    if not os.path.exists('config.ini'):
        raise FileNotFoundError("配置文件 config.ini 未找到！")
    config.read('config.ini', encoding='utf-8')
    return config


@app.route('/')
def index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'index.html')


@app.route('/style.css')
def serve_style():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'style.css')


@app.route('/script.js')
def serve_script():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'script.js')


@app.route('/favicon.ico')
def favicon():
    return ('', 204)


def init_gemini():
    global model, chat_session, system_prompt, civ6_config, mod_log_path
    app.logger.info("正在初始化 Gemini...")
    config = load_config()

    api_key = config.get("Gemini", "api_key", fallback=None)
    http_proxy = config.get("Proxy", "http_proxy", fallback=None)
    system_prompt = config.get("Prompt", "system_prompt", fallback="你是一位資深的文明6玩家。")

    civ6_config = Civ6ContextConfig(
        enabled=config.getboolean("Civ6", "enabled", fallback=True),
        save_dir=config.get("Civ6", "save_dir", fallback="").strip(),
        max_context_chars=config.getint("Civ6", "max_context_chars", fallback=12000),
        include_payload_metadata=config.getboolean("Civ6", "include_payload_metadata", fallback=True),
    )
    mod_log_path = config.get("Civ6", "lua_log", fallback="").strip()

    if not api_key or api_key == "YOUR_GEMINI_API_KEY":
        raise ValueError("請在 config.ini 文件中設定 Gemini API Key！")

    if http_proxy:
        app.logger.info(f"使用代理: {http_proxy}")
        os.environ['http_proxy'] = http_proxy
        os.environ['https_proxy'] = http_proxy

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-pro')
    chat_session = model.start_chat(history=[
        {'role': 'user', 'parts': [system_prompt]},
        {'role': 'model', 'parts': ["好的，我已經準備好了。請隨時向我展示截圖並提出問題。"]}
    ])
    app.logger.info("Gemini 初始化成功！")


@app.route('/log-stream')
def log_stream():
    def generate():
        while True:
            if stream_handler.queue:
                yield f"data: {stream_handler.queue.pop(0)}\n\n"
            time.sleep(0.1)
    return Response(generate(), mimetype='text/event-stream')


@app.route('/game-state', methods=['GET'])
def game_state():
    context = build_context(civ6_config)
    context["ui_mod"] = latest_snapshot(mod_log_path)
    status = 200 if context.get("status") in ("ok", "disabled") or context["ui_mod"].get("status") == "ok" else 404
    return jsonify(context), status


@app.route('/mod-state', methods=['GET'])
def mod_state():
    snapshot = latest_snapshot(mod_log_path)
    return jsonify(snapshot), 200 if snapshot.get("status") == "ok" else 404


@app.route('/game-state/diagnostics', methods=['GET'])
def game_state_diagnostics():
    context = build_context(civ6_config, include_diagnostics=True)
    status = 200 if context.get("status") in ("ok", "disabled") else 404
    return jsonify(context), status


@app.route('/game-state/full-map', methods=['GET'])
def game_state_full_map():
    context = build_context(civ6_config)
    status = 200 if context.get("status") in ("ok", "disabled") else 404
    if status != 200:
        return jsonify(context), status

    full = context.get("_deep_state_full")
    if not full:
        return jsonify({
            "status": "deep_state_unavailable",
            "error": context.get("deep_state_error"),
            "header": context.get("header"),
        }), 422

    return jsonify({
        "status": "ok",
        "file_name": context.get("file_name"),
        "header": context.get("header"),
        "deep_state": full,
    })


@app.route('/chat', methods=['POST'])
def handle_chat():
    data = request.json or {}
    question = data.get('question')
    image_b64 = data.get('image')

    if not question:
        return jsonify({"error": "問題不能為空"}), 400

    app.logger.info(f"收到聊天請求，包含圖片: {'是' if image_b64 else '否'}")

    def generate_responses():
        try:
            prompt_parts = []

            snapshot = latest_snapshot(mod_log_path)
            if snapshot.get("status") == "ok":
                prompt_parts.append(snapshot_for_prompt(snapshot))
                prompt_parts.append("請依據當前回合、領袖與文明能力、城市、單位與已探索地塊回答。依序提供可執行的勝利路線、城市落點、生產、區域布局、科技與市政建議；逐項列出坐標、依據、前置條件與替代方案。未提供的地圖、建造合法性及解鎖條件須明確標為待遊戲內確認；不要推測未探索區域。若快照與存檔回合不一致，優先採用較新的遊戲內快照。")

            game_context = build_context(civ6_config)
            if game_context.get("status") == "ok":
                app.logger.info(f"已載入 Civ6 存檔 context: {game_context.get('file_name')}")
                if snapshot.get("status") == "ok":
                    prompt_parts.append("存檔僅供交叉核對回合與設定；遊戲內快照優先。" +
                                        str({"header": game_context.get("header"),
                                             "file_name": game_context.get("file_name")}))
                else:
                    prompt_parts.append(context_for_prompt(game_context, civ6_config.max_context_chars))
            else:
                app.logger.info(f"Civ6 存檔 context 未使用: {game_context.get('status')}")

            prompt_parts.append(question)

            if image_b64:
                app.logger.info("解碼圖片資料...")
                image_data = base64.b64decode(image_b64)
                prompt_parts.append({"mime_type": "image/png", "data": image_data})

            app.logger.info("向 Gemini 發送流式請求...")
            responses = chat_session.send_message(prompt_parts, stream=True)
            for chunk in responses:
                if getattr(chunk, "text", None):
                    yield f"data: {chunk.text}\n\n"
            app.logger.info("流式響應結束。")
        except Exception as e:
            app.logger.error(f"流式響應出錯: {e}")
            yield f"data: **發生錯誤**: {e}\n\n"

    return Response(generate_responses(), mimetype='text/event-stream')


@app.route('/screenshot', methods=['GET'])
def take_screenshot():
    app.logger.info("收到截圖請求...")
    try:
        screenshot = ImageGrab.grab()
        buffer = io.BytesIO()
        screenshot.save(buffer, format='PNG')
        img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
        app.logger.info("截圖成功並已編碼為 Base64。")
        return jsonify({"image": img_str})
    except Exception as e:
        app.logger.error(f"截圖失敗: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    try:
        init_gemini()
        app.run(host='127.0.0.1', port=5001, debug=False)
    except (FileNotFoundError, ValueError) as e:
        print(f"啟動失敗: {e}")
