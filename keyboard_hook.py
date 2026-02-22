"""全局键盘钩子模块 - 监听键盘按键长按事件.

支持多种按键：CAPS LOCK、左/右Ctrl、左/右Alt、左/右Shift等
"""

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from pynput import keyboard


@dataclass
class KeyboardEvent:
    """键盘事件数据类."""
    
    event_type: str  # 'press', 'hold', 'release'
    key: str  # 按键名称
    duration_ms: int = 0
    timestamp: float = 0.0


class KeyboardHook:
    """
    全局键盘钩子，监听指定按键的长按事件.
    
    特性:
    - 支持多种按键（Ctrl、Alt、Shift、Caps Lock等）
    - 检测按键按下
    - 超过阈值时触发hold事件
    - 检测按键释放
    - 支持设置长按阈值
    """
    
    # 支持的按键映射
    KEY_MAP = {
        'caps_lock': keyboard.Key.caps_lock,
        'ctrl': keyboard.Key.ctrl,
        'ctrl_l': keyboard.Key.ctrl_l,
        'ctrl_r': keyboard.Key.ctrl_r,
        'alt': keyboard.Key.alt,
        'alt_l': keyboard.Key.alt_l,
        'alt_r': keyboard.Key.alt_r,
        'shift': keyboard.Key.shift,
        'shift_l': keyboard.Key.shift_l,
        'shift_r': keyboard.Key.shift_r,
        'cmd': keyboard.Key.cmd,
        'cmd_l': keyboard.Key.cmd_l,
        'cmd_r': keyboard.Key.cmd_r,
        'tab': keyboard.Key.tab,
        'space': keyboard.Key.space,
        'enter': keyboard.Key.enter,
        'esc': keyboard.Key.esc,
        'f1': keyboard.Key.f1,
        'f2': keyboard.Key.f2,
        'f3': keyboard.Key.f3,
        'f4': keyboard.Key.f4,
        'f5': keyboard.Key.f5,
        'f6': keyboard.Key.f6,
        'f7': keyboard.Key.f7,
        'f8': keyboard.Key.f8,
        'f9': keyboard.Key.f9,
        'f10': keyboard.Key.f10,
        'f11': keyboard.Key.f11,
        'f12': keyboard.Key.f12,
    }
    
    def __init__(
        self,
        trigger_key: str = 'ctrl_r',
        hold_threshold_ms: int = 500,
        on_press: Optional[Callable[[KeyboardEvent], None]] = None,
        on_hold: Optional[Callable[[KeyboardEvent], None]] = None,
        on_release: Optional[Callable[[KeyboardEvent], None]] = None
    ):
        """初始化键盘钩子.
        
        Args:
            trigger_key: 触发按键，如 'ctrl_r' (右Ctrl), 'caps_lock', 'ctrl_l' 等
            hold_threshold_ms: 长按阈值(毫秒)，默认500ms
            on_press: 按键按下回调
            on_hold: 按键长按超过阈值回调
            on_release: 按键释放回调
        """
        if trigger_key not in self.KEY_MAP:
            raise ValueError(f"不支持的按键: {trigger_key}. 支持: {list(self.KEY_MAP.keys())}")
        
        self.trigger_key = trigger_key
        self.target_key = self.KEY_MAP[trigger_key]
        self.hold_threshold_ms = hold_threshold_ms
        self.on_press = on_press
        self.on_hold = on_hold
        self.on_release = on_release
        
        self._is_pressed = False
        self._hold_triggered = False
        self._press_time: Optional[float] = None
        self._listener: Optional[keyboard.Listener] = None
        self._hold_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
    
    def _on_key_press(self):
        """处理按键按下事件."""
        with self._lock:
            if not self._is_pressed:
                self._is_pressed = True
                self._hold_triggered = False
                self._press_time = time.time()
                
                # 触发press事件
                if self.on_press:
                    event = KeyboardEvent(
                        event_type='press',
                        key=self.trigger_key,
                        duration_ms=0,
                        timestamp=self._press_time
                    )
                    self._trigger_callback(self.on_press, event)
                
                # 启动定时器检测长按
                self._hold_timer = threading.Timer(
                    self.hold_threshold_ms / 1000.0,
                    self._on_hold_timeout
                )
                self._hold_timer.daemon = True
                self._hold_timer.start()
    
    def _on_key_release(self):
        """处理按键释放事件."""
        with self._lock:
            if self._is_pressed:
                # 取消定时器
                if self._hold_timer:
                    self._hold_timer.cancel()
                    self._hold_timer = None
                
                # 计算按压时长
                duration_ms = 0
                if self._press_time:
                    duration_ms = int((time.time() - self._press_time) * 1000)
                
                self._is_pressed = False
                
                # 触发release事件
                if self.on_release:
                    event = KeyboardEvent(
                        event_type='release',
                        key=self.trigger_key,
                        duration_ms=duration_ms,
                        timestamp=time.time()
                    )
                    self._trigger_callback(self.on_release, event)
                
                self._press_time = None
    
    def _on_hold_timeout(self):
        """长按超时处理."""
        with self._lock:
            if self._is_pressed and not self._hold_triggered:
                self._hold_triggered = True
                
                # 计算按压时长
                duration_ms = 0
                if self._press_time:
                    duration_ms = int((time.time() - self._press_time) * 1000)
                
                # 触发hold事件
                if self.on_hold:
                    event = KeyboardEvent(
                        event_type='hold',
                        key=self.trigger_key,
                        duration_ms=duration_ms,
                        timestamp=time.time()
                    )
                    self._trigger_callback(self.on_hold, event)
    
    def _trigger_callback(
        self, 
        callback: Callable[[KeyboardEvent], None], 
        event: KeyboardEvent
    ):
        """在线程中触发回调."""
        threading.Thread(target=callback, args=(event,), daemon=True).start()
    
    def _on_press(self, key):
        """键盘按下回调."""
        try:
            if key == self.target_key:
                self._on_key_press()
        except Exception as e:
            print(f"键盘按下处理错误: {e}")
    
    def _on_release(self, key):
        """键盘释放回调."""
        try:
            if key == self.target_key:
                self._on_key_release()
        except Exception as e:
            print(f"键盘释放处理错误: {e}")
    
    def start(self):
        """启动键盘监听."""
        key_name = self._get_key_display_name()
        print(f"启动键盘监听，按键: {key_name}, 长按阈值: {self.hold_threshold_ms}ms")
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
            suppress=False
        )
        self._listener.start()
    
    def _get_key_display_name(self) -> str:
        """获取按键的显示名称."""
        display_names = {
            'caps_lock': 'Caps Lock',
            'ctrl': 'Ctrl',
            'ctrl_l': '左Ctrl',
            'ctrl_r': '右Ctrl',
            'alt': 'Alt',
            'alt_l': '左Alt',
            'alt_r': '右Alt',
            'shift': 'Shift',
            'shift_l': '左Shift',
            'shift_r': '右Shift',
            'cmd': 'Win/Cmd',
            'cmd_l': '左Win/Cmd',
            'cmd_r': '右Win/Cmd',
            'tab': 'Tab',
            'space': '空格',
            'enter': '回车',
            'esc': 'Esc',
        }
        return display_names.get(self.trigger_key, self.trigger_key.upper())
    
    def stop(self):
        """停止键盘监听."""
        print("停止键盘监听")
        if self._listener:
            self._listener.stop()
            self._listener = None
        
        if self._hold_timer:
            self._hold_timer.cancel()
            self._hold_timer = None
        
        self._is_pressed = False
    
    def is_running(self) -> bool:
        """检查是否在运行."""
        return self._listener is not None and self._listener.is_alive()


# 兼容旧的 CapsLockHook 类名
CapsLockHook = KeyboardHook


# 简单的测试代码
if __name__ == "__main__":
    import sys
    
    def on_press(event: KeyboardEvent):
        print(f"[{event.timestamp:.3f}] {event.key} 按下")
    
    def on_hold(event: KeyboardEvent):
        print(f"[{event.timestamp:.3f}] {event.key} 长按触发! 持续 {event.duration_ms}ms")
    
    def on_release(event: KeyboardEvent):
        print(f"[{event.timestamp:.3f}] {event.key} 释放，总时长 {event.duration_ms}ms")
    
    print("测试键盘钩子")
    print("- 按住右Ctrl超过500ms触发长按")
    print("- 按Ctrl+C退出")
    print()
    
    hook = KeyboardHook(
        trigger_key='ctrl_r',  # 右Ctrl
        hold_threshold_ms=500,
        on_press=on_press,
        on_hold=on_hold,
        on_release=on_release
    )
    hook.start()
    
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n退出...")
        hook.stop()
        sys.exit(0)
