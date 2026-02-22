# Windows语音输入客户端

基于 Qwen3-ASR 的 Windows 实时语音输入工具，支持鼠标、键盘、触摸板多种触发方式。

> 📁 返回主项目: [README.md](../README.md)

## 功能特性

- 🖱️ **多种触发方式**: 支持鼠标中键/侧键、键盘（Ctrl/Alt/Shift/F1-F12）、触摸板手势
- 🎤 **长按触发**: 按住触发键超过设定时间自动开始录音
- 📝 **实时流式识别**: 基于 WebSocket 协议，低延迟实时转写
- 💻 **自动上屏**: 识别结果自动输入到当前活动窗口
- 🌐 **多语言支持**: 支持 30 种语言（中文、英语、日语、韩语、粤语等）
- ☁️ **多ASR服务商**: 支持本地 Qwen3-ASR 和阿里云智能语音交互
- 🔄 **自动重连**: 网络中断时自动重连服务器
- ⚙️ **可配置**: 通过配置文件自定义各项参数
- 🎯 **智能窗口识别**: 自动识别终端/浏览器/游戏/Office窗口
- 📁 **音频文件导入**: 支持从音频文件识别语音

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置服务器和触发方式

编辑 `voice_input/config.ini`:

```ini
[server]
ws_url = ws://localhost:8080
language = auto  # 自动检测语言，或指定具体语言如 Chinese, English
enable_punctuation = true
enable_itn = true

[trigger]
# 触发方式: mouse, keyboard, touchpad
type = keyboard
# 键盘按键: caps_lock, ctrl_l, ctrl_r, alt_l, alt_r, shift_l, shift_r, f1-f12
button = ctrl_r
hold_threshold_ms = 500

[input]
use_clipboard = true
show_intermediate = false
```

### 3. 运行程序

```bash
cd voice_input
python voice_input_app.py
```

## 使用方法

### 键盘触发（推荐）

**右CTRL键（默认配置）:**
1. **开始录音**: 按住右 CTRL 键超过 500ms
2. **说话**: 对着麦克风说话
3. **停止录音**: 释放右 CTRL 键
4. **自动上屏**: 识别结果自动输入到当前活动窗口

**其他按键选项:**
- `ctrl_l` - 左 Ctrl
- `ctrl_r` - 右 Ctrl（推荐，与其他快捷键不冲突）
- `alt_l`, `alt_r` - 左/右 Alt
- `shift_l`, `shift_r` - 左/右 Shift
- `caps_lock` - Caps Lock
- `f1` - `f12` - 功能键

### 鼠标触发

**鼠标中键:**
1. 按住鼠标中键（滚轮按下）超过设定时间开始录音
2. 释放停止录音

**鼠标侧键:**
- `x1` - 侧键-后退（拇指位置靠前的按键）
- `x2` - 侧键-前进（拇指位置靠后的按键）

### 触摸板手势

**三指点击（默认）:**
1. 使用三指点击触摸板超过设定时间开始录音
2. 释放停止录音

**其他手势:**
- `single` - 单指点击
- `double` - 双指点击
- `triple` - 三指点击（默认）
- `quadruple` - 四指点击
- `edge_swipe` - 边缘轻扫

### 音频文件导入

支持从音频文件识别语音：

```bash
# 基本用法
python audio_recognize.py audio.wav

# 指定服务器和语言
python audio_recognize.py audio.wav --url ws://127.0.0.1:8080 --lang zh-CN

# 保存结果到文件
python audio_recognize.py audio.wav -o result.txt
```

## 智能窗口识别

程序能自动识别目标窗口类型并选择最佳输入方式：

| 窗口类型 | 检测方式 | 输入方式 |
|---------|---------|---------|
| 终端 | 进程名(cmd.exe, powershell.exe, npm.exe...) + 类名(ConsoleWindowClass, CASCADIA...) + 标题关键词 | 剪贴板(Ctrl+Shift+V / Ctrl+V) |
| 浏览器 | 进程名(chrome.exe, msedge.exe...) + 类名 | 剪贴板 |
| 游戏 | 标题关键词 | SendInput |
| Office | 标题关键词 | 剪贴板 |
| 普通窗口 | 默认 | 剪贴板 |

### 终端支持

支持的终端进程：
- `powershell.exe`, `pwsh.exe`, `cmd.exe`
- `node.exe`, `npm.exe`, `python.exe`
- `WindowsTerminal.exe`, `mintty.exe`

支持的终端类名：
- `ConsoleWindowClass` (CMD/PowerShell)
- `CASCADIA_HOSTING_WINDOW_CLASS` (VSCode终端)
- `mintty` (Git Bash)

## 项目结构

```
voice_input/
├── __init__.py                 # 包初始化
├── voice_input_app.py          # 主程序
├── keyboard_hook.py            # 全局键盘钩子
├── mouse_hook.py               # 全局鼠标钩子
├── touchpad_hook.py            # 触摸板手势钩子
├── caps_lock_hook.py           # Caps Lock 钩子
├── audio_capture.py            # 音频采集模块
├── asr_client.py               # ASR WebSocket客户端（本地）
├── ali_asr_client.py           # 阿里云 ASR 客户端
├── ali_asr_protocol.md         # 阿里云 ASR 协议文档
├── text_input.py               # 文本输入模块
├── ime_input.py                # 智能文本输入（自动窗口识别）
├── audio_recognize.py          # 音频文件识别工具
├── audio_file_recognizer.py    # 音频识别模块
├── config.ini                  # 配置文件
└── README.md                   # 本文档
```

## 模块说明

### voice_input_app.py
主程序入口，整合所有模块实现完整的语音输入功能。

```bash
# 运行主程序
python voice_input_app.py

# 查看帮助
python voice_input_app.py --help
```

启动后：
1. 加载配置文件
2. 初始化 ASR 客户端（本地或阿里云）
3. 设置触发器（鼠标/键盘/触摸板）
4. 等待触发事件
5. 录音并识别
6. 自动输入识别结果

### ime_input.py
智能文本输入模块，自动检测窗口类型并选择最佳输入方式。

```python
from ime_input import SmartTextInput

inputter = SmartTextInput()
inputter.send_text("你好世界！")  # 自动检测窗口类型
```

### audio_recognize.py
音频文件识别工具。

```bash
python audio_recognize.py audio.wav -o result.txt
```

### asr_client.py
ASR WebSocket 客户端，实现流式语音识别协议（本地 Qwen3-ASR）。

```python
from asr_client import ASRClient

def on_result(text, is_final):
    print(f"{'最终' if is_final else '中间'}: {text}")

client = ASRClient(
    ws_url="ws://localhost:8080",
    language="auto",
    on_result=on_result
)
client.start()
```

### ali_asr_client.py
阿里云智能语音交互客户端，实现阿里云 WebSocket 实时语音识别协议。

```python
from ali_asr_client import AliASRClient

def on_result(text, is_final):
    print(f"{'最终' if is_final else '中间'}: {text}")

client = AliASRClient(
    token="your_token",
    appkey="your_appkey",
    on_result=on_result
)
client.start()
```

详见 [ali_asr_protocol.md](ali_asr_protocol.md)

## 配置说明

### 服务器配置 [server]

| 参数 | 说明 | 默认值 |
|------|------|--------|
| provider | ASR服务提供商: local 或 ali | local |
| ws_url | WebSocket 服务器地址（local模式） | ws://127.0.0.1:8080 |
| ali_token | 阿里云访问Token（ali模式） | - |
| ali_appkey | 阿里云 AppKey（ali模式） | - |
| ali_gateway | 阿里云网关地址 | wss://nls-gateway-cn-shanghai.aliyuncs.com/ws/v1 |
| language | 语言设置（auto 或具体语言） | zh-CN |
| enable_punctuation | 启用标点符号 | true |
| enable_itn | 启用数字转换 | true |

### 使用阿里云 ASR

1. 在阿里云开通智能语音交互服务
2. 获取 Token 和 AppKey：https://help.aliyun.com/zh/isi/overview-of-obtaining-an-access-token
3. 修改 `config.ini`：

```ini
[server]
provider = ali
ali_token = 你的Token
ali_appkey = 你的Appkey
```

### 触发配置 [trigger]

| 参数 | 说明 | 默认值 |
|------|------|--------|
| type | 触发类型: mouse, keyboard, touchpad | mouse |
| button | 触发按键/手势 | middle |
| hold_threshold_ms | 长按阈值（毫秒） | 500 |

### 智能窗口检测配置 [input]

```ini
# 终端检测（优先级: 进程名 > 类名 > 标题）
terminal_processes = powershell.exe, pwsh.exe, cmd.exe, node.exe, npm.exe, python.exe
terminal_classes = ConsoleWindowClass, CASCADIA_HOSTING_WINDOW_CLASS, mintty
terminal_keywords = powershell, cmd, terminal, npm, vscode

# 浏览器检测
browser_processes = chrome.exe, firefox.exe, msedge.exe
browser_classes = Chrome_WidgetWin_1, MozillaWindowClass

# 输入方式: clipboard 或 sendinput
terminal_input_method = clipboard
browser_input_method = clipboard
normal_input_method = clipboard
game_input_method = sendinput
office_input_method = clipboard
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| terminal_processes | 终端进程名列表 | powershell.exe, cmd.exe... |
| terminal_classes | 终端窗口类名列表 | ConsoleWindowClass... |
| terminal_keywords | 终端标题关键词 | powershell, cmd... |
| *_input_method | 各类型窗口的输入方式 | clipboard |

### 音频配置 [audio]

| 参数 | 说明 | 默认值 |
|------|------|--------|
| chunk_duration_ms | 音频块时长（毫秒） | 100 |

## 系统要求

- Windows 10/11
- Python 3.8+
- 麦克风设备
- ASR 服务器（Qwen3-ASR）

## 故障排除

### 无法连接到服务器
- 检查 `ws_url` 配置是否正确
- 确认网络连接正常
- 检查服务器是否运行
- 检查防火墙是否允许 8080 端口

### 按键无法触发
- 检查 `type` 和 `button` 配置是否正确
- 以管理员身份运行程序
- 检查是否有其他程序占用了键盘/鼠标钩子

### 文本未能上屏
- 查看日志确认窗口类型识别结果
- 检查目标窗口是否被正确识别
- 尝试使用 `sendinput` 输入方式

### 终端上屏失败
- 确认终端类名在配置中
- VSCode内置终端使用 `CASCADIA_HOSTING_WINDOW_CLASS`

### 音频采集失败
- 检查麦克风权限
- 确认麦克风设备可用
- 尝试其他录音软件测试

## 最佳实践

### 办公场景（推荐）
```ini
[trigger]
type = keyboard
button = ctrl_r
hold_threshold_ms = 500
```

### 笔记本外出
```ini
[trigger]
type = touchpad
gesture = triple
hold_threshold_ms = 300
```

### 游戏场景
```ini
[input]
game_input_method = sendinput
```

## 开发计划

- [ ] 系统托盘图标
- [ ] 可视化录音指示器
- [x] 音频文件导入
- [x] 智能窗口识别
- [x] 终端窗口类名检测
- [x] 触摸板手势支持
- [x] 多种键盘按键支持
- [x] 30种语言支持

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
