
# Civ6-GPT-Assistant - 文明6 AI助手

![App Screenshot](screenshots/1.png)

一款专为《文明6》玩家设计的桌面智能助手。通过即时截图和强大的AI分析，为您的游戏决策提供实时、专业的策略建议。

---

## ✨ 主要功能

- **一键截图分析**: 在游戏窗口模式下，点击一下按钮即可捕捉当前游戏画面。
- **AI策略建议**: 集成 Google 最新的 Gemini 2.5 Pro 模型，为您分析当前局势，从科技、市政、军事、外交等多个维度提供深度建议。
- **纯文本聊天**: 无需截图，也可以随时向AI顾问提问，获取关于游戏机制、奇观、领袖特性等的解答。
- **流式响应**: AI的回答以打字机效果逐字显示，极大降低等待时间，提供流畅的交互体验。
- **富文本展示**: 支持Markdown格式，让AI的回答重点突出、条理清晰。
- **可配置化**: 支持配置网络代理和自定义系统提示(System Prompt)，满足个性化需求。
- **实时调试面板**: 内置后端日志面板，方便开发者进行二次开发和调试。

## 🛠️ 技术栈

- **后端**: Python + Flask
- **AI模型**: Google Gemini 2.5 Pro
- **前端**: HTML, CSS, JavaScript (原生)
- **桌面端打包 (规划中)**: Tauri

## 🚀 如何使用 (开发模式)

本项目目前在开发模式下运行，您可以通过以下步骤在本地启动它：

### 1. 克隆或下载项目

将本项目代码下载到您的本地电脑。

### 2. 配置环境

- **安装 Python**: 确保您的电脑上已安装 Python 3.8+。
- **安装依赖**: 打开命令行，进入项目根目录，然后运行以下命令来安装所需的Python库：
  ```bash
  pip install -r requirements.txt
  ```

### 3. 创建并配置 `config.ini`

- 在项目根目录下，找到 `config.ini.example` 文件。
- **复制**并**重命名**该文件为 `config.ini`。
- 打开新的 `config.ini` 文件，填入您的信息：
  - `api_key`: 填入您自己的 Google Gemini API 密钥。
  - `http_proxy`: 如果您需要通过代理访问网络，请填写您的代理地址 (例如 `http://127.0.0.1:7890`)，否则请留空。
  - `system_prompt`: 您可以按需修改对AI的系统指令。

### 4. 启动应用

一切准备就绪后，您需要通过两个步骤来启动应用：

- **启动后端服务**: 在项目根目录的命令行中，运行：
  ```bash
  python app.py
  ```
  请保持此命令行窗口不要关闭，它就是应用的“大脑”。

- **打开前端界面**: 在您的文件浏览器中，直接**双击打开 `index.html` 文件**。您的默认浏览器会自动打开应用界面。

现在，您就可以开始使用了！

## 📝 未来计划

- [ ] 使用 Tauri 将应用打包成独立的 `.exe` 可执行文件，实现真正的桌面级体验。
- [ ] 增加聊天历史记录的本地存储功能。
- [ ] 进一步美化UI，增加更多主题选项。

## 🤝 贡献

欢迎提交 Pull Requests 或 Issues 来为这个项目做出贡献！

## 📄 开源许可

本项目采用 [MIT License](LICENSE) 开源许可。


## 🧠 Save Context v1

本 fork 在原本「截圖 + Gemini」流程之外，新增 Civilization VI 存檔 Context：

- 每次送出問題時，自動搜尋最新的 `.Civ6Save`
- 解析目前可可靠取得的 `game_turn`、`game_speed`、`map_size`
- 嘗試解壓 game-data payload，僅作診斷與輔助，不把未確認的 binary 欄位當成精確遊戲狀態
- 結構化資料會和使用者問題、截圖一起送給 Gemini
- 解析失敗時自動退回原本的截圖模式

### 設定

複製 `config.ini.example` 成 `config.ini`，並填入 Gemini API Key。

```ini
[Civ6]
enabled = true
save_dir =
max_context_chars = 12000
include_payload_metadata = true
```

`save_dir` 留空時，會自動搜尋 Windows 常見的 Civ6 存檔路徑與 OneDrive Documents。

啟動後可以用：

```
http://127.0.0.1:5001/game-state
```

確認目前偵測到的存檔與解析結果。

### 測試

```bash
python test_save_context.py
```

若輸出 `PASS`，代表第一版 parser 的基本功能正常。
