"""全局键盘钩子模块 - 监听CAPS LOCK长按事件."""

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from pynput import keyboard


@dataclass
class CapsLockEvent:
    """CAPS LOCK事件数据类."""
    
    event_type: str  # 'press', 'hold', 'release'
    duration_ms: int = 0
    timestamp: float = 0.0


class CapsLockHook:
    """
    全局键盘钩子，监听CAPS LOCK长按事件.
    
    特性:
    - 检测CAPS按下
    - 超过阈值时触发hold事件
    - 检测CAPS释放
    - 支持设置长按阈值
    """
    
    def __init__(
        self,
        hold_threshold_ms: int = 500,
        on_press: Optional[Callable[[CapsLockEvent], None]] = None,
        on_hold: Optional[Callable[[CapsLockEvent], None]] = None,
        on_release: Optional[Callable[[CapsLockEvent], None]] = None
    ):
        """初始化键盘钩子.
        
        Args:
            hold_threshold_ms: 长按阈值(毫秒)，默认500ms
            on_press: CAPS按下回调
            on_hold: CAPS长按超过阈值回调
            on_release: CAPS释放回调
        """
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
    
    def _on_caps_press(self):
        """处理CAPS按下事件."""
        with self._lock:
            if not self._is_pressed:
                self._is_pressed = True
                self._hold_triggered = False
                self._press_time = time.time()
                
                # 触发press事件
                if self.on_press:
                    event = CapsLockEvent(
                        event_type='press',
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
    
    def _on_caps_release(self):
        """处理CAPS释放事件."""
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
                    event = CapsLockEvent(
                        event_type='release',
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
                    event = CapsLockEvent(
                        event_type='hold',
                        duration_ms=duration_ms,
                        timestamp=time.time()
                    )
                    self._trigger_callback(self.on_hold, event)
    
    def _trigger_callback(
        self, 
        callback: Callable[[CapsLockEvent], None], 
        event: CapsLockEvent
    ):
        """在线程中触发回调."""
        threading.Thread(target=callback, args=(event,), daemon=True).start()
    
    def _on_press(self, key):
        """键盘按下回调."""
        try:
            if key == keyboard.Key.caps_lock:
                self._on_caps_press()
        except Exception as e:
            print(f"键盘按下处理错误: {e}")
    
    def _on_release(self, key):
        """键盘释放回调."""
        try:
            if key == keyboard.Key.caps_lock:
                self._on_caps_release()
        except Exception as e:
            print(f"键盘释放处理错误: {e}")
    
    def start(self):
        """启动键盘监听."""
        print(f"启动键盘监听，长按阈值: {self.hold_threshold_ms}ms")
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
            suppress=False
        )
        self._listener.start()
    
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


# 简单的测试代码
if __name__ == "__main__":
    import sys
    
    def on_press(event: CapsLockEvent):
        print(f"[{event.timestamp:.3f}] CAPS 按下")
    
    def on_hold(event: CapsLockEvent):
        print(f"[{event.timestamp:.3f}] CAPS 长按触发! 持续 {event.duration_ms}ms")
    
    def on_release(event: CapsLockEvent):
        print(f"[{event.timestamp:.3f}] CAPS 释放，总时长 {event.duration_ms}ms")
    
    print("测试CAPS LOCK钩子")
    print("- 按住CAPS LOCK超过500ms触发长按")
    print("- 按Ctrl+C退出")
    print()
    
    hook = CapsLockHook(
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
