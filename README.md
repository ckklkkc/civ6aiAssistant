
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

## 遊戲內 Steam 模組：局勢匯出與策略建議

此倉庫新增 `steam_mod/Civ6Assistant`，可作為 Civ VI 的本機 UI 模組安裝；尚未發佈到 Steam Workshop。它在畫面右上加入「匯出局勢」按鈕，擷取**本地玩家目前看得到**的城市、單位，以及城市和開拓者附近三格內的可見地塊。資料包含文明與領袖特性識別碼、當前研發、城市人口與住房、地塊座標、地形、資源及產出。它只讀資料，不會替玩家下指令。

### Windows 安裝

1. 把整個 `steam_mod/Civ6Assistant` 資料夾複製到 `%USERPROFILE%\Documents\My Games\Sid Meier's Civilization VI\Mods\`；若「文件」位於 OneDrive，改用 OneDrive 的 `Documents\My Games\...\Mods`。模組資料夾內應直接看見 `Civ6Assistant.modinfo`。
2. 在 Civ VI「額外內容／模組」啟用 **Civ VI Assistant - 局勢匯出**，重新進入遊戲。
3. 按遊戲右上「匯出局勢」。開啟 `http://127.0.0.1:5001/mod-state` 應看見 `"status": "ok"` 和目前回合；接著在現有聊天頁面詢問「我該在哪裡建城？如何規劃學院？」。
4. 如系統找不到 `Lua.log`，先檢查 `%LOCALAPPDATA%\Firaxis Games\Sid Meier's Civilization VI\Logs\Lua.log`（新版本位置）及 `%USERPROFILE%\Documents\My Games\Sid Meier's Civilization VI\Logs\Lua.log`（舊位置）。如使用其他路徑，在 `config.ini` 的 `[Civ6]` 設定 `lua_log = C:\...\Lua.log`，重啟 `python app.py`。

這個 UI 模組會將有標記的資料寫入遊戲既有的 Lua 日誌，由 Flask 本機服務讀取；遊戲模組本身不直接連網，也不接觸 API Key。截圖仍由原本網頁按鈕擷取桌面；若要問的是特定格的 UI 建造合法性，請附上遊戲截圖。每次回合或局勢改變後，重新按「匯出局勢」。完整資料可透過 `/mod-state` 檢查；聊天提示會因長度限制截取部分地塊。

### 局限與驗證

- 地塊候選清單不等於遊戲的建城或區域合法位置；推薦位置須在遊戲介面確認前置科技、距離、領土、區域限制和 DLC 規則。
- 模組尚未在實際 Windows／Steam 遊戲中執行驗證；XML、Python 與模擬日誌已做靜態及單元檢查。第一次啟用時若看不到按鈕，請查看 `Lua.log` 中的 `CIV6_ASSISTANT` 與錯誤訊息。
- 不依賴存檔深層地圖解析。若遊戲內快照可用，聊天只拿存檔標頭交叉核對，避免把尚未驗證的深層資料當成事實。

```bash
python test_mod_bridge.py
```
