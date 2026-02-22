"""文本输入模块 - 将识别结果上屏到活动窗口."""

import ctypes
import time
from ctypes import wintypes
from typing import Optional

import win32api
import win32con
import win32gui


# SendInput API 定义
INPUT_KEYBOARD = 1
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002


# ULONG_PTR 定义（兼容32位和64位）
if ctypes.sizeof(ctypes.c_void_p) == 8:
    ULONG_PTR = ctypes.c_ulonglong
else:
    ULONG_PTR = ctypes.c_ulong


class KEYBDINPUT(ctypes.Structure):
    """键盘输入结构体."""
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class INPUT_I(ctypes.Union):
    """INPUT联合体."""
    _fields_ = [
        ("ki", KEYBDINPUT),
    ]


class INPUT(ctypes.Structure):
    """输入结构体."""
    _anonymous_ = ("_input",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("_input", INPUT_I),
    ]


class TextInput:
    """
    文本输入器，将文本发送到Windows活动窗口.
    
    特性:
    - 使用SendInput API（支持Unicode，更可靠）
    - 剪贴板方式作为降级方案
    - 模拟键盘输入（兼容性备用）
    """
    
    # 键盘扫描码映射（备用方案）
    KEY_MAP = {
        'a': 0x1E, 'b': 0x30, 'c': 0x2E, 'd': 0x20,
        'e': 0x12, 'f': 0x21, 'g': 0x22, 'h': 0x23,
        'i': 0x17, 'j': 0x24, 'k': 0x25, 'l': 0x26,
        'm': 0x32, 'n': 0x31, 'o': 0x18, 'p': 0x19,
        'q': 0x10, 'r': 0x13, 's': 0x1F, 't': 0x14,
        'u': 0x16, 'v': 0x2F, 'w': 0x11, 'x': 0x2D,
        'y': 0x15, 'z': 0x2C,
        '0': 0x0B, '1': 0x02, '2': 0x03, '3': 0x04,
        '4': 0x05, '5': 0x06, '6': 0x07, '7': 0x08,
        '8': 0x09, '9': 0x0A,
        ' ': 0x39, ',': 0x33, '.': 0x34, '/': 0x35,
        ';': 0x27, "'": 0x28, '[': 0x1A, ']': 0x1B,
        '-': 0x0C, '=': 0x0D, '\\': 0x2B,
        '\n': 0x1C, '\t': 0x0F,
    }
    
    SHIFT_KEYS = {
        '~': '`', '!': '1', '@': '2', '#': '3', '$': '4',
        '%': '5', '^': '6', '&': '7', '*': '8', '(': '9',
        ')': '0', '_': '-', '+': '=', '{': '[', '}': ']',
        '|': '\\', ':': ';', '"': "'", '<': ',', '>': '.',
        '?': '/',
    }
    
    def __init__(self, delay_ms: float = 10.0):
        """初始化文本输入器.
        
        Args:
            delay_ms: 按键间隔（毫秒）
        """
        self.delay_ms = delay_ms / 1000.0  # 转换为秒
        self._send_input = ctypes.windll.user32.SendInput
        self._send_input.argtypes = [
            wintypes.UINT,
            ctypes.POINTER(INPUT),
            ctypes.c_int
        ]
        self._send_input.restype = wintypes.UINT
    
    def get_active_window_title(self) -> Optional[str]:
        """获取活动窗口标题.
        
        Returns:
            窗口标题或None
        """
        try:
            hwnd = win32gui.GetForegroundWindow()
            return win32gui.GetWindowText(hwnd)
        except Exception as e:
            print(f"获取窗口标题失败: {e}")
            return None
    
    def send_text(self, text: str, use_clipboard: bool = False) -> bool:
        """发送文本到活动窗口.
        
        使用降级策略:
        1. 优先使用 SendInput (最可靠，支持Unicode)
        2. 失败时回退到剪贴板
        3. 最后尝试模拟键盘（仅ASCII）
        
        Args:
            text: 要发送的文本
            use_clipboard: 是否强制使用剪贴板（默认优先SendInput）
            
        Returns:
            是否成功
        """
        if not text:
            return False
        
        try:
            window_title = self.get_active_window_title()
            print(f"发送到窗口: {window_title}")
            
            # 策略1: 优先使用 SendInput（除非强制使用剪贴板）
            if not use_clipboard:
                print("尝试使用 SendInput...")
                if self._send_via_sendinput(text):
                    print("✓ SendInput 成功")
                    return True
                print("✗ SendInput 失败，回退到剪贴板")
            
            # 策略2: 使用剪贴板
            if self._send_via_clipboard(text):
                print("✓ 剪贴板成功")
                return True
            print("✗ 剪贴板失败，回退到模拟键盘")
            
            # 策略3: 使用模拟键盘（仅ASCII）
            if self._send_via_keyboard(text):
                print("✓ 模拟键盘成功")
                return True
            
            print("✗ 所有方法都失败")
            return False
                
        except Exception as e:
            print(f"发送文本失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _send_via_sendinput(self, text: str) -> bool:
        """使用SendInput API发送Unicode文本.
        
        SendInput 比 keybd_event 更底层、更可靠，
        支持直接发送Unicode字符，无需剪贴板。
        
        Args:
            text: 要发送的文本（支持任意Unicode字符）
            
        Returns:
            是否成功
        """
        try:
            inputs = []
            
            for char in text:
                # 获取字符的Unicode码点
                code_point = ord(char)
                
                # 创建按键按下事件
                key_down = INPUT()
                key_down.type = INPUT_KEYBOARD
                key_down.ki.wVk = 0
                key_down.ki.wScan = code_point
                key_down.ki.dwFlags = KEYEVENTF_UNICODE
                key_down.ki.time = 0
                key_down.ki.dwExtraInfo = 0
                
                # 创建按键释放事件
                key_up = INPUT()
                key_up.type = INPUT_KEYBOARD
                key_up.ki.wVk = 0
                key_up.ki.wScan = code_point
                key_up.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
                key_up.ki.time = 0
                key_up.ki.dwExtraInfo = 0
                
                inputs.append(key_down)
                inputs.append(key_up)
            
            # 将输入数组转换为ctypes数组
            nInputs = len(inputs)
            LPINPUT = INPUT * nInputs
            pInputs = LPINPUT(*inputs)
            
            # 调用SendInput
            cbSize = ctypes.sizeof(INPUT)
            result = self._send_input(nInputs, pInputs, cbSize)
            
            if result == nInputs:
                return True
            else:
                print(f"SendInput 部分失败: 发送 {result}/{nInputs} 个事件")
                return result > 0
                
        except Exception as e:
            print(f"SendInput 错误: {e}")
            return False
    
    def _send_via_clipboard(self, text: str) -> bool:
        """通过剪贴板发送文本（支持中文）.
        
        Args:
            text: 要发送的文本
            
        Returns:
            是否成功
        """
        try:
            import win32clipboard
            
            # 保存原始剪贴板内容
            win32clipboard.OpenClipboard()
            try:
                original_data = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            except:
                original_data = ""
            win32clipboard.CloseClipboard()
            
            # 设置新文本到剪贴板
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            
            # 模拟Ctrl+V粘贴（使用SendInput更可靠）
            self._send_key_combination([win32con.VK_CONTROL, ord('V')])
            
            time.sleep(0.1)
            
            # 恢复原始剪贴板内容
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            if original_data:
                win32clipboard.SetClipboardText(original_data, win32con.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            
            return True
            
        except Exception as e:
            print(f"剪贴板操作失败: {e}")
            return False
    
    def _send_key_combination(self, keys: list):
        """发送组合键.
        
        Args:
            keys: 虚拟键码列表
        """
        try:
            inputs = []
            
            # 按下所有键
            for key in keys:
                key_down = INPUT()
                key_down.type = INPUT_KEYBOARD
                key_down.ki.wVk = key
                key_down.ki.wScan = 0
                key_down.ki.dwFlags = 0
                key_down.ki.time = 0
                key_down.ki.dwExtraInfo = 0
                inputs.append(key_down)
            
            # 释放所有键（逆序）
            for key in reversed(keys):
                key_up = INPUT()
                key_up.type = INPUT_KEYBOARD
                key_up.ki.wVk = key
                key_up.ki.wScan = 0
                key_up.ki.dwFlags = KEYEVENTF_KEYUP
                key_up.ki.time = 0
                key_up.ki.dwExtraInfo = 0
                inputs.append(key_up)
            
            nInputs = len(inputs)
            LPINPUT = INPUT * nInputs
            pInputs = LPINPUT(*inputs)
            cbSize = ctypes.sizeof(INPUT)
            
            self._send_input(nInputs, pInputs, cbSize)
            time.sleep(0.05)
            
        except Exception as e:
            print(f"发送组合键失败: {e}")
            # 回退到 keybd_event
            for key in keys:
                win32api.keybd_event(key, 0, 0, 0)
            time.sleep(0.05)
            for key in reversed(keys):
                win32api.keybd_event(key, 0, win32con.KEYEVENTF_KEYUP, 0)
    
    def _send_via_keyboard(self, text: str) -> bool:
        """通过模拟键盘发送文本（仅支持ASCII字符）.
        
        Args:
            text: 要发送的文本
            
        Returns:
            是否成功
        """
        try:
            for char in text:
                self._send_char(char)
                time.sleep(self.delay_ms)
            
            return True
            
        except Exception as e:
            print(f"键盘输入失败: {e}")
            return False
    
    def _send_char(self, char: str):
        """发送单个字符.
        
        Args:
            char: 字符
        """
        char_lower = char.lower()
        
        # 检查是否需要Shift
        need_shift = char in self.SHIFT_KEYS or char.isupper()
        
        if char in self.SHIFT_KEYS:
            char = self.SHIFT_KEYS[char]
            char_lower = char.lower()
        
        # 获取扫描码
        if char_lower in self.KEY_MAP:
            scan_code = self.KEY_MAP[char_lower]
            
            # 按下Shift（如果需要）
            if need_shift:
                self._key_down(win32con.VK_SHIFT)
            
            # 按下并释放按键
            self._scan_key(scan_code)
            
            # 释放Shift
            if need_shift:
                self._key_up(win32con.VK_SHIFT)
        else:
            # 未知字符，尝试直接发送
            print(f"警告: 未知字符 '{char}'，跳过")
    
    def _scan_key(self, scan_code: int):
        """发送扫描码按键.
        
        Args:
            scan_code: 扫描码
        """
        # 按键按下
        win32api.keybd_event(0, scan_code, 0, 0)
        time.sleep(0.01)
        # 按键释放
        win32api.keybd_event(0, scan_code, win32con.KEYEVENTF_KEYUP, 0)
    
    def _key_down(self, vk_code: int):
        """虚拟键码按下.
        
        Args:
            vk_code: 虚拟键码
        """
        win32api.keybd_event(vk_code, 0, 0, 0)
    
    def _key_up(self, vk_code: int):
        """虚拟键码释放.
        
        Args:
            vk_code: 虚拟键码
        """
        win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)
    
    def send_key(self, vk_code: int):
        """发送单个虚拟键码.
        
        Args:
            vk_code: 虚拟键码
        """
        try:
            # 优先使用 SendInput
            inputs = []
            
            key_down = INPUT()
            key_down.type = INPUT_KEYBOARD
            key_down.ki.wVk = vk_code
            key_down.ki.wScan = 0
            key_down.ki.dwFlags = 0
            key_down.ki.time = 0
            key_down.ki.dwExtraInfo = 0
            inputs.append(key_down)
            
            key_up = INPUT()
            key_up.type = INPUT_KEYBOARD
            key_up.ki.wVk = vk_code
            key_up.ki.wScan = 0
            key_up.ki.dwFlags = KEYEVENTF_KEYUP
            key_up.ki.time = 0
            key_up.ki.dwExtraInfo = 0
            inputs.append(key_up)
            
            nInputs = len(inputs)
            LPINPUT = INPUT * nInputs
            pInputs = LPINPUT(*inputs)
            cbSize = ctypes.sizeof(INPUT)
            
            self._send_input(nInputs, pInputs, cbSize)
            time.sleep(0.01)
            
        except Exception as e:
            # 回退到 keybd_event
            self._key_down(vk_code)
            time.sleep(0.01)
            self._key_up(vk_code)
    
    def send_enter(self):
        """发送回车键."""
        self.send_key(win32con.VK_RETURN)
    
    def send_backspace(self, count: int = 1):
        """发送退格键.
        
        Args:
            count: 退格次数
        """
        for _ in range(count):
            self.send_key(win32con.VK_BACK)
            time.sleep(self.delay_ms)


# 测试代码
if __name__ == "__main__":
    import sys
    
    print("测试文本输入模块（SendInput版本）")
    print("- 请在3秒内点击要输入的窗口")
    print("- 测试将输入: 'Hello World! 你好世界！'")
    print()
    
    for i in range(3, 0, -1):
        print(f"{i}...")
        time.sleep(1)
    
    text_input = TextInput(delay_ms=50)
    
    # 测试混合文本（中英文+标点）
    print("\n测试混合文本输入...")
    text_input.send_text("Hello World! 你好世界！123")
    time.sleep(0.5)
    
    # 测试退格
    print("测试退格...")
    text_input.send_backspace(3)
    time.sleep(0.3)
    
    # 测试回车
    print("测试回车...")
    text_input.send_enter()
    time.sleep(0.3)
    
    # 测试特殊字符
    print("测试特殊字符...")
    text_input.send_text("@#$%^&*()_+-=[]{}|;':\",./<>?")
    
    print("\n测试完成！")
