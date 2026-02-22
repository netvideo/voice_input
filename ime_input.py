"""智能文本输入模块 - 根据目标窗口自动选择最佳输入方式."""

import ctypes
import time
import configparser
from typing import Optional, Tuple

import win32api
import win32con
import win32gui
import win32clipboard


INPUT_KEYBOARD = 1
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_ulonglong),
    ]


class INPUT_I(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("_input",)
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("_input", INPUT_I),
    ]


class SmartTextInput:
    """智能文本输入器 - 根据窗口类型自动选择最佳输入方式."""
    
    # 默认配置
    DEFAULT_TERMINAL_KEYWORDS = [
        "powershell", "cmd", "pwsh", "windows terminal",
        "windowsterminal", "conemu", "conhost", "mintty",
        "gitbash", "anaconda", "anacondaprompt", "terminal"
    ]
    
    # 终端进程名（高优先级）
    DEFAULT_TERMINAL_PROCESSES = [
        "powershell.exe", "pwsh.exe", "cmd.exe", "conhost.exe",
        "WindowsTerminal.exe", "OpenConsole.exe", "wt.exe",
        "mintty.exe", "git-bash.exe", "anaconda-navigator.exe",
        "python.exe", "pythonw.exe", "node.exe", "npm.exe",
        "yarn.exe", "pnpm.exe", "bun.exe",
    ]
    
    # 终端窗口类名（高优先级）
    DEFAULT_TERMINAL_CLASSES = [
        "ConsoleWindowClass",  # CMD/PowerShell
        "mintty",  # Git Bash
        "PuTTY",  # SSH客户端
        "WindowsTerminal",  # Windows Terminal
    ]
    
    DEFAULT_BROWSER_KEYWORDS = [
        "chrome", "firefox", "edge", "safari", "brave", "opera"
    ]
    
    DEFAULT_BROWSER_PROCESSES = [
        "chrome.exe", "firefox.exe", "msedge.exe", "brave.exe",
        "opera.exe", "safari.exe"
    ]
    
    DEFAULT_BROWSER_CLASSES = [
        "Chrome_WidgetWin_1", "MozillaWindowClass", "Browser_Server"
    ]
    
    DEFAULT_GAME_KEYWORDS = [
        "unreal", "unity", "steam", "gog", "epic", "directx", "opengl"
    ]
    
    DEFAULT_OFFICE_KEYWORDS = [
        "winword", "excel", "powerpoint", "outlook"
    ]
    
    def __init__(self, config_path: str = "config.ini", delay_ms: float = 5.0):
        """初始化智能文本输入器.
        
        Args:
            config_path: 配置文件路径
            delay_ms: 按键间隔（毫秒）
        """
        self.delay_ms = delay_ms / 1000.0
        self.user32 = ctypes.windll.user32
        self._send_input = self.user32.SendInput
        
        # 从配置文件加载设置
        self._load_config(config_path)
    
    def _load_config(self, config_path: str):
        """从配置文件加载设置."""
        self.terminal_keywords = self.DEFAULT_TERMINAL_KEYWORDS.copy()
        self.terminal_processes = self.DEFAULT_TERMINAL_PROCESSES.copy()
        self.terminal_classes = self.DEFAULT_TERMINAL_CLASSES.copy()
        
        self.game_keywords = self.DEFAULT_GAME_KEYWORDS.copy()
        
        self.browser_keywords = self.DEFAULT_BROWSER_KEYWORDS.copy()
        self.browser_processes = self.DEFAULT_BROWSER_PROCESSES.copy()
        self.browser_classes = self.DEFAULT_BROWSER_CLASSES.copy()
        
        self.office_keywords = self.DEFAULT_OFFICE_KEYWORDS.copy()
        
        self.input_methods = {
            "terminal": "clipboard",
            "browser": "clipboard",
            "normal": "clipboard",
            "game": "sendinput",
            "office": "clipboard",
        }
        
        try:
            config = configparser.ConfigParser()
            config.read(config_path, encoding="utf-8")
            
            # 终端关键词
            if config.has_option("input", "terminal_keywords"):
                keywords = config.get("input", "terminal_keywords")
                self.terminal_keywords = [k.strip().lower() for k in keywords.split(",") if k.strip()]
            
            # 终端进程名
            if config.has_option("input", "terminal_processes"):
                processes = config.get("input", "terminal_processes")
                self.terminal_processes = [p.strip().lower() for p in processes.split(",") if p.strip()]
            
            # 终端窗口类名
            if config.has_option("input", "terminal_classes"):
                classes = config.get("input", "terminal_classes")
                self.terminal_classes = [c.strip().lower() for c in classes.split(",") if c.strip()]
            
            # 游戏关键词
            if config.has_option("input", "game_keywords"):
                keywords = config.get("input", "game_keywords")
                self.game_keywords = [k.strip().lower() for k in keywords.split(",") if k.strip()]
            
            # 浏览器关键词
            if config.has_option("input", "browser_keywords"):
                keywords = config.get("input", "browser_keywords")
                self.browser_keywords = [k.strip().lower() for k in keywords.split(",") if k.strip()]
            
            # 浏览器进程名
            if config.has_option("input", "browser_processes"):
                processes = config.get("input", "browser_processes")
                self.browser_processes = [p.strip().lower() for p in processes.split(",") if p.strip()]
            
            # Office关键词
            if config.has_option("input", "office_keywords"):
                keywords = config.get("input", "office_keywords")
                self.office_keywords = [k.strip().lower() for k in keywords.split(",") if k.strip()]
            
            # 输入方式
            if config.has_option("input", "terminal_input_method"):
                self.input_methods["terminal"] = config.get("input", "terminal_input_method")
            if config.has_option("input", "browser_input_method"):
                self.input_methods["browser"] = config.get("input", "browser_input_method")
            if config.has_option("input", "normal_input_method"):
                self.input_methods["normal"] = config.get("input", "normal_input_method")
            if config.has_option("input", "game_input_method"):
                self.input_methods["game"] = config.get("input", "game_input_method")
            if config.has_option("input", "office_input_method"):
                self.input_methods["office"] = config.get("input", "office_input_method")
            
            print(f"[SmartTextInput] 配置已加载")
            print(f"  终端关键词: {self.terminal_keywords}")
            print(f"  终端进程: {self.terminal_processes}")
            print(f"  终端类名: {self.terminal_classes}")
            print(f"  游戏关键词: {self.game_keywords}")
            print(f"  浏览器关键词: {self.browser_keywords}")
            print(f"  浏览器进程: {self.browser_processes}")
            print(f"  Office关键词: {self.office_keywords}")
            print(f"  输入方式: {self.input_methods}")
            
        except Exception as e:
            print(f"[SmartTextInput] 加载配置失败，使用默认配置: {e}")
    
    def get_window_info(self) -> Tuple[Optional[int], str]:
        """获取活动窗口信息."""
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        class_name = self._get_class_name(hwnd)
        process_name = self._get_process_name(hwnd)
        return hwnd, f"{title} ({class_name}) - {process_name}"
    
    def _get_class_name(self, hwnd: int) -> str:
        try:
            buf = ctypes.create_unicode_buffer(256)
            self.user32.GetClassNameW(hwnd, buf, 256)
            return buf.value
        except:
            return ""
    
    def _get_process_name(self, hwnd: int) -> str:
        try:
            _, pid = self.user32.GetWindowThreadProcessId(hwnd, None)
            handle = ctypes.windll.kernel32.OpenProcess(0x0400, False, pid)
            if handle:
                buf = ctypes.create_unicode_buffer(256)
                ctypes.windll.psapi.GetModuleBaseNameW(handle, None, buf, 256)
                ctypes.windll.kernel32.CloseHandle(handle)
                return buf.value
        except:
            pass
        return ""
    
    def detect_window_type(self, hwnd: int, title: str, process: str, class_name: str = None) -> str:
        """检测窗口类型 (优先级: 进程名 > 类名 > 标题关键词).
        
        Args:
            hwnd: 窗口句柄
            title: 窗口标题
            process: 进程名
            class_name: 窗口类名
        """
        if class_name is None:
            class_name = self._get_class_name(hwnd)
        
        title_lower = title.lower()
        process_lower = process.lower()
        class_lower = class_name.lower()
        
        # ===== 终端检测 (最高优先级) =====
        # 1. 检查进程名 (最可靠)
        if any(proc in process_lower for proc in self.terminal_processes):
            return "terminal"
        
        # 2. 检查窗口类名
        if any(cls in class_lower for cls in self.terminal_classes):
            return "terminal"
        
        # 3. 检查窗口标题关键词
        if any(keyword in title_lower for keyword in self.terminal_keywords):
            return "terminal"
        
        # ===== 浏览器检测 =====
        # 1. 检查进程名
        if any(proc in process_lower for proc in self.browser_processes):
            return "browser"
        
        # 2. 检查窗口类名
        if any(cls in class_lower for cls in self.browser_classes):
            return "browser"
        
        # 3. 检查窗口标题
        if any(keyword in title_lower for keyword in self.browser_keywords):
            return "browser"
        
        # ===== 游戏检测 =====
        if any(keyword in title_lower for keyword in self.game_keywords):
            return "game"
        
        # ===== Office检测 =====
        if any(keyword in title_lower for keyword in self.office_keywords):
            return "office"
        
        # 默认普通窗口
        return "normal"
    
    def send_text(self, text: str) -> bool:
        """发送文本到活动窗口（根据配置文件智能选择方式）."""
        if not text:
            return False
        
        hwnd, info = self.get_window_info()
        if not hwnd:
            print("没有活动窗口")
            return False
        
        title = win32gui.GetWindowText(hwnd)
        process = self._get_process_name(hwnd)
        class_name = self._get_class_name(hwnd)
        win_type = self.detect_window_type(hwnd, title, process, class_name)
        
        print(f"输入到: {info}")
        print(f"窗口类型: {win_type}, 输入方式: {self.input_methods.get(win_type, 'clipboard')}")
        
        # 先激活窗口
        self._activate_window(hwnd)
        
        # 获取该窗口类型的输入方式
        method = self.input_methods.get(win_type, "clipboard")
        
        # 根据输入方式发送
        if method == "sendinput":
            if self._send_via_sendinput(text):
                print("✓ SendInput 成功")
                return True
        else:  # clipboard
            if win_type == "terminal":
                if self._send_via_clipboard_terminal(text):
                    print("✓ 剪贴板成功")
                    return True
            else:
                if self._send_via_clipboard(text):
                    print("✓ 剪贴板成功")
                    return True
        
        # 失败时尝试另一种方式
        if method == "sendinput":
            if self._send_via_clipboard(text):
                print("✓ 备选剪贴板成功")
                return True
        else:
            if self._send_via_sendinput(text):
                print("✓ 备选SendInput成功")
                return True
        
        print("所有方法都失败")
        return False
    
    def _send_via_clipboard_terminal(self, text: str) -> bool:
        """使用剪贴板发送到终端."""
        try:
            original = self._get_clipboard()
            
            # 设置剪贴板
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            
            time.sleep(0.05)
            
            # 方式1: Ctrl+Shift+V (大多数Linux/WSL终端)
            print("  尝试 Ctrl+Shift+V...")
            if self._send_ctrl_shift_v():
                time.sleep(0.2)
                self._restore_clipboard(original)
                return True
            
            # 方式2: Ctrl+V (Windows终端/PowerShell)
            print("  尝试 Ctrl+V...")
            if self._send_ctrl_v():
                time.sleep(0.2)
                self._restore_clipboard(original)
                return True
            
            # 方式3: Alt+空格 -> E -> P (旧版Windows)
            print("  尝试 Alt+空格+P...")
            if self._send_alt_space_paste():
                time.sleep(0.2)
                self._restore_clipboard(original)
                return True
            
            # 恢复剪贴板
            self._restore_clipboard(original)
            return True
            
        except Exception as e:
            print(f"  终端剪贴板错误: {e}")
            return False
    
    def _send_ctrl_shift_v(self) -> bool:
        """模拟 Ctrl+Shift+V."""
        try:
            win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
            win32api.keybd_event(win32con.VK_SHIFT, 0, 0, 0)
            time.sleep(0.03)
            win32api.keybd_event(ord('V'), 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(ord('V'), 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(win32con.VK_SHIFT, 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            return True
        except:
            return False
    
    def _send_ctrl_v(self) -> bool:
        """模拟 Ctrl+V."""
        try:
            win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
            time.sleep(0.03)
            win32api.keybd_event(ord('V'), 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(ord('V'), 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            return True
        except:
            return False
    
    def _send_alt_space_paste(self) -> bool:
        """模拟 Alt+空格 -> P (右键菜单粘贴)."""
        try:
            # Alt+空格
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(ord(' '), 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(ord(' '), 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.1)
            
            # P (粘贴)
            win32api.keybd_event(ord('P'), 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(ord('P'), 0, win32con.KEYEVENTF_KEYUP, 0)
            
            # 释放Alt
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
            return True
        except:
            return False
    
    def _activate_window(self, hwnd: int) -> bool:
        """激活窗口."""
        try:
            self.user32.SetForegroundWindow(hwnd)
            time.sleep(0.1)
            return True
        except:
            return False
    
    def _send_via_clipboard(self, text: str) -> bool:
        """使用剪贴板发送文本."""
        try:
            original = self._get_clipboard()
            
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            
            self._send_ctrl_v()
            time.sleep(0.1)
            
            self._restore_clipboard(original)
            return True
        except Exception as e:
            print(f"  剪贴板错误: {e}")
            return False
    
    def _get_clipboard(self) -> str:
        try:
            win32clipboard.OpenClipboard()
            data = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            return data
        except:
            return ""
    
    def _restore_clipboard(self, text: str):
        try:
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            if text:
                win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
        except:
            pass
    
    def _send_via_sendinput(self, text: str) -> bool:
        """使用SendInput发送文本."""
        try:
            input_array = (INPUT * (len(text) * 2))()
            
            idx = 0
            for char in text:
                code = ord(char)
                
                down = INPUT()
                down.type = INPUT_KEYBOARD
                down.ki.wVk = 0
                down.ki.wScan = code
                down.ki.dwFlags = KEYEVENTF_UNICODE
                down.ki.time = 0
                down.ki.dwExtraInfo = 0
                input_array[idx] = down
                idx += 1
                
                up = INPUT()
                up.type = INPUT_KEYBOARD
                up.ki.wVk = 0
                up.ki.wScan = code
                up.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
                up.ki.time = 0
                up.ki.dwExtraInfo = 0
                input_array[idx] = up
                idx += 1
            
            self._send_input(idx, input_array, ctypes.sizeof(INPUT))
            return True
        except Exception as e:
            print(f"  SendInput错误: {e}")
            return False
    
    def send_backspace(self, count: int = 1) -> bool:
        """发送退格键."""
        for _ in range(count):
            win32api.keybd_event(win32con.VK_BACK, 0, 0, 0)
            time.sleep(self.delay_ms)
            win32api.keybd_event(win32con.VK_BACK, 0, win32con.KEYEVENTF_KEYUP, 0)
        return True


# 测试代码
if __name__ == "__main__":
    print("智能文本输入测试")
    print("- 请在3秒内点击终端窗口")
    print()
    
    for i in range(3, 0, -1):
        print(f"{i}...")
        time.sleep(1)
    
    text_input = SmartTextInput()
    
    hwnd, info = text_input.get_window_info()
    print(f"\n检测到窗口: {info}")
    
    print("\n测试文本输入...")
    text_input.send_text("echo 你好世界")
    time.sleep(0.3)
    
    print("\n测试退格...")
    text_input.send_backspace(5)
    
    print("\n测试完成！")
