"""全局鼠标钩子模块 - 监听鼠标中键长按事件."""

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from pynput import mouse


@dataclass
class MouseEvent:
    """鼠标事件数据类."""
    
    event_type: str  # 'press', 'hold', 'release'
    button: str  # 'middle', 'x1', 'x2', 'left', 'right'
    duration_ms: int = 0
    timestamp: float = 0.0
    x: int = 0
    y: int = 0


class MouseHook:
    """
    全局鼠标钩子，监听指定按键的长按事件.
    
    特性:
    - 支持鼠标中键、侧键(X1/X2)、左右键
    - 检测按下、长按、释放
    - 可配置长按阈值
    - 记录鼠标位置
    """
    
    # 支持的按键映射
    BUTTON_MAP = {
        'middle': mouse.Button.middle,
        'left': mouse.Button.left,
        'right': mouse.Button.right,
        'x1': mouse.Button.x1,  # 侧键-后退
        'x2': mouse.Button.x2,  # 侧键-前进
    }
    
    def __init__(
        self,
        trigger_button: str = 'middle',
        hold_threshold_ms: int = 500,
        on_press: Optional[Callable[[MouseEvent], None]] = None,
        on_hold: Optional[Callable[[MouseEvent], None]] = None,
        on_release: Optional[Callable[[MouseEvent], None]] = None
    ):
        """初始化鼠标钩子.
        
        Args:
            trigger_button: 触发按键，可选 'middle', 'left', 'right', 'x1', 'x2'
            hold_threshold_ms: 长按阈值(毫秒)，默认500ms
            on_press: 按键按下回调
            on_hold: 按键长按超过阈值回调
            on_release: 按键释放回调
        """
        if trigger_button not in self.BUTTON_MAP:
            raise ValueError(f"不支持的按键: {trigger_button}. 支持: {list(self.BUTTON_MAP.keys())}")
        
        self.trigger_button = trigger_button
        self.target_button = self.BUTTON_MAP[trigger_button]
        self.hold_threshold_ms = hold_threshold_ms
        self.on_press = on_press
        self.on_hold = on_hold
        self.on_release = on_release
        
        self._is_pressed = False
        self._hold_triggered = False
        self._press_time: Optional[float] = None
        self._press_position: tuple = (0, 0)
        self._listener: Optional[mouse.Listener] = None
        self._hold_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
    
    def _on_button_press(self, x: int, y: int):
        """处理按键按下事件."""
        with self._lock:
            if not self._is_pressed:
                self._is_pressed = True
                self._hold_triggered = False
                self._press_time = time.time()
                self._press_position = (x, y)
                
                # 触发press事件
                if self.on_press:
                    event = MouseEvent(
                        event_type='press',
                        button=self.trigger_button,
                        duration_ms=0,
                        timestamp=self._press_time,
                        x=x,
                        y=y
                    )
                    self._trigger_callback(self.on_press, event)
                
                # 启动定时器检测长按
                self._hold_timer = threading.Timer(
                    self.hold_threshold_ms / 1000.0,
                    self._on_hold_timeout,
                    args=(x, y)
                )
                self._hold_timer.daemon = True
                self._hold_timer.start()
    
    def _on_button_release(self, x: int, y: int):
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
                    event = MouseEvent(
                        event_type='release',
                        button=self.trigger_button,
                        duration_ms=duration_ms,
                        timestamp=time.time(),
                        x=x,
                        y=y
                    )
                    self._trigger_callback(self.on_release, event)
                
                self._press_time = None
    
    def _on_hold_timeout(self, x: int, y: int):
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
                    event = MouseEvent(
                        event_type='hold',
                        button=self.trigger_button,
                        duration_ms=duration_ms,
                        timestamp=time.time(),
                        x=x,
                        y=y
                    )
                    self._trigger_callback(self.on_hold, event)
    
    def _trigger_callback(
        self, 
        callback: Callable[[MouseEvent], None], 
        event: MouseEvent
    ):
        """在线程中触发回调."""
        threading.Thread(target=callback, args=(event,), daemon=True).start()
    
    def _on_click(self, x: int, y: int, button: mouse.Button, pressed: bool):
        """鼠标点击回调."""
        try:
            if button == self.target_button:
                if pressed:
                    self._on_button_press(x, y)
                else:
                    self._on_button_release(x, y)
        except Exception as e:
            print(f"鼠标点击处理错误: {e}")
    
    def start(self):
        """启动鼠标监听."""
        print(f"启动鼠标监听，触发键: {self.trigger_button}, 长按阈值: {self.hold_threshold_ms}ms")
        self._listener = mouse.Listener(
            on_click=self._on_click,
            suppress=False
        )
        self._listener.start()
    
    def stop(self):
        """停止鼠标监听."""
        print("停止鼠标监听")
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
    
    def on_press(event: MouseEvent):
        print(f"[{event.timestamp:.3f}] {event.button} 按下 @ ({event.x}, {event.y})")
    
    def on_hold(event: MouseEvent):
        print(f"[{event.timestamp:.3f}] {event.button} 长按触发! 持续 {event.duration_ms}ms @ ({event.x}, {event.y})")
    
    def on_release(event: MouseEvent):
        print(f"[{event.timestamp:.3f}] {event.button} 释放，总时长 {event.duration_ms}ms @ ({event.x}, {event.y})")
    
    print("测试鼠标中键钩子")
    print("- 按住鼠标中键超过500ms触发长按")
    print("- 也支持侧键 (x1/x2)，修改 trigger_button 参数测试")
    print("- 按Ctrl+C退出")
    print()
    
    hook = MouseHook(
        trigger_button='middle',  # 可改为 'x1' 或 'x2' 测试侧键
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
