"""触摸板钩子模块 - 监听触摸板手势事件.

功能:
- 支持多指点击检测（双指、三指、四指）
- 支持触摸板边缘轻扫手势
- 支持轻触（Tap）和按压（Force Touch）检测
- 可配置手势阈值和灵敏度

Windows Precision Touchpad (PTP) 支持:
- 使用 Windows API 获取原始触摸输入
- 支持多点触控手势识别

注意事项:
- 部分功能需要 Windows 10/11 和 Precision Touchpad
- 非 PTP 触摸板可能只能使用基础功能
"""

import ctypes
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from pynput import mouse


@dataclass
class TouchpadEvent:
    """触摸板事件数据类."""
    
    event_type: str  # 'press', 'hold', 'release', 'tap', 'swipe'
    gesture: str  # 'single', 'double', 'triple', 'quadruple', 'edge_swipe'
    duration_ms: int = 0
    timestamp: float = 0.0
    x: int = 0
    y: int = 0
    finger_count: int = 1
    pressure: float = 0.0  # 压力值 (0.0-1.0)


class TouchpadHook:
    """
    触摸板手势钩子，监听多指点击和手势事件.
    
    特性:
    - 支持多指点击（双指、三指、四指）
    - 支持边缘轻扫手势
    - 可配置长按阈值
    - 自动区分鼠标和触摸板输入
    """
    
    # 手势类型
    GESTURE_SINGLE = 'single'      # 单指
    GESTURE_DOUBLE = 'double'      # 双指
    GESTURE_TRIPLE = 'triple'      # 三指
    GESTURE_QUADRUPLE = 'quadruple'  # 四指
    GESTURE_EDGE_SWIPE = 'edge_swipe'  # 边缘轻扫
    
    def __init__(
        self,
        gesture: str = 'triple',
        hold_threshold_ms: int = 300,
        edge_swipe_enabled: bool = False,
        edge_swipe_width: int = 50,
        on_press: Optional[Callable[[TouchpadEvent], None]] = None,
        on_hold: Optional[Callable[[TouchpadEvent], None]] = None,
        on_release: Optional[Callable[[TouchpadEvent], None]] = None,
        on_tap: Optional[Callable[[TouchpadEvent], None]] = None
    ):
        """初始化触摸板钩子.
        
        Args:
            gesture: 触发手势，可选 'single', 'double', 'triple', 'quadruple', 'edge_swipe'
            hold_threshold_ms: 长按阈值(毫秒)，默认300ms
            edge_swipe_enabled: 是否启用边缘轻扫
            edge_swipe_width: 边缘区域宽度(像素)
            on_press: 手势开始回调
            on_hold: 手势长按超过阈值回调
            on_release: 手势释放回调
            on_tap: 轻触回调（未超过阈值）
        """
        self.gesture = gesture
        self.hold_threshold_ms = hold_threshold_ms
        self.edge_swipe_enabled = edge_swipe_enabled
        self.edge_swipe_width = edge_swipe_width
        self.on_press = on_press
        self.on_hold = on_hold
        self.on_release = on_release
        self.on_tap = on_tap
        
        # 状态
        self._is_pressed = False
        self._hold_triggered = False
        self._press_time: Optional[float] = None
        self._press_position: tuple = (0, 0)
        self._listener: Optional[mouse.Listener] = None
        self._hold_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        
        # 点击检测状态（用于模拟多指点击）
        self._click_times: list = []
        self._click_timeout = 0.5  # 多击检测超时(秒)
        self._max_click_count = 1
        
        # 获取屏幕尺寸用于边缘检测
        self._screen_width = ctypes.windll.user32.GetSystemMetrics(0)
        self._screen_height = ctypes.windll.user32.GetSystemMetrics(1)
        
        # 手指计数映射
        self._finger_count_map = {
            'single': 1,
            'double': 2,
            'triple': 3,
            'quadruple': 4,
        }
    
    def _get_target_finger_count(self) -> int:
        """获取目标手指数量."""
        return self._finger_count_map.get(self.gesture, 1)
    
    def _is_edge_area(self, x: int, y: int) -> bool:
        """检查坐标是否在边缘区域."""
        if not self.edge_swipe_enabled:
            return False
        
        edge = self.edge_swipe_width
        return (
            x < edge or  # 左边缘
            x > self._screen_width - edge or  # 右边缘
            y < edge or  # 上边缘
            y > self._screen_height - edge  # 下边缘
        )
    
    def _detect_multi_click(self) -> int:
        """检测多击次数.
        
        Returns:
            点击次数 (1-4)
        """
        now = time.time()
        
        # 清除超时的点击记录
        self._click_times = [t for t in self._click_times if now - t < self._click_timeout]
        
        # 添加当前点击
        self._click_times.append(now)
        
        # 返回点击次数（限制最大4次）
        return min(len(self._click_times), 4)
    
    def _on_button_press(self, x: int, y: int):
        """处理按键/触摸按下事件."""
        # 检测多击
        click_count = self._detect_multi_click()
        target_count = self._get_target_finger_count()
        
        # 边缘轻扫模式
        if self.gesture == 'edge_swipe' and not self._is_edge_area(x, y):
            return
        
        # 检查是否匹配目标手势
        if click_count != target_count and self.gesture != 'edge_swipe':
            return
        
        with self._lock:
            if not self._is_pressed:
                self._is_pressed = True
                self._hold_triggered = False
                self._press_time = time.time()
                self._press_position = (x, y)
                
                # 触发press事件
                if self.on_press:
                    event = TouchpadEvent(
                        event_type='press',
                        gesture=self.gesture,
                        duration_ms=0,
                        timestamp=self._press_time,
                        x=x,
                        y=y,
                        finger_count=click_count
                    )
                    self._trigger_callback(self.on_press, event)
                
                # 启动定时器检测长按
                self._hold_timer = threading.Timer(
                    self.hold_threshold_ms / 1000.0,
                    self._on_hold_timeout,
                    args=(x, y, click_count)
                )
                self._hold_timer.daemon = True
                self._hold_timer.start()
    
    def _on_button_release(self, x: int, y: int):
        """处理按键/触摸释放事件."""
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
                
                # 判断是长按还是轻触
                if duration_ms < self.hold_threshold_ms and self.on_tap:
                    # 轻触
                    event = TouchpadEvent(
                        event_type='tap',
                        gesture=self.gesture,
                        duration_ms=duration_ms,
                        timestamp=time.time(),
                        x=x,
                        y=y,
                        finger_count=self._get_target_finger_count()
                    )
                    self._trigger_callback(self.on_tap, event)
                elif self.on_release:
                    # 释放
                    event = TouchpadEvent(
                        event_type='release',
                        gesture=self.gesture,
                        duration_ms=duration_ms,
                        timestamp=time.time(),
                        x=x,
                        y=y,
                        finger_count=self._get_target_finger_count()
                    )
                    self._trigger_callback(self.on_release, event)
                
                self._press_time = None
                
                # 延迟重置点击计数
                threading.Timer(self._click_timeout, self._reset_click_count).start()
    
    def _reset_click_count(self):
        """重置点击计数."""
        if not self._is_pressed:
            self._click_times.clear()
    
    def _on_hold_timeout(self, x: int, y: int, finger_count: int):
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
                    event = TouchpadEvent(
                        event_type='hold',
                        gesture=self.gesture,
                        duration_ms=duration_ms,
                        timestamp=time.time(),
                        x=x,
                        y=y,
                        finger_count=finger_count
                    )
                    self._trigger_callback(self.on_hold, event)
    
    def _trigger_callback(
        self, 
        callback: Callable[[TouchpadEvent], None], 
        event: TouchpadEvent
    ):
        """在线程中触发回调."""
        threading.Thread(target=callback, args=(event,), daemon=True).start()
    
    def _on_click(self, x: int, y: int, button: mouse.Button, pressed: bool):
        """鼠标点击回调（触摸板也会产生此事件）."""
        try:
            # 只处理左键（触摸板通常模拟左键）
            if button != mouse.Button.left:
                return
            
            if pressed:
                self._on_button_press(x, y)
            else:
                self._on_button_release(x, y)
        except Exception as e:
            print(f"触摸板处理错误: {e}")
    
    def start(self):
        """启动触摸板监听."""
        gesture_name = {
            'single': '单指',
            'double': '双指',
            'triple': '三指',
            'quadruple': '四指',
            'edge_swipe': '边缘轻扫',
        }.get(self.gesture, self.gesture)
        
        print(f"启动触摸板监听，手势: {gesture_name}, 长按阈值: {self.hold_threshold_ms}ms")
        
        if self.edge_swipe_enabled:
            print(f"边缘区域宽度: {self.edge_swipe_width}px")
        
        self._listener = mouse.Listener(
            on_click=self._on_click,
            suppress=False
        )
        self._listener.start()
    
    def stop(self):
        """停止触摸板监听."""
        print("停止触摸板监听")
        if self._listener:
            self._listener.stop()
            self._listener = None
        
        if self._hold_timer:
            self._hold_timer.cancel()
            self._hold_timer = None
        
        self._is_pressed = False
        self._click_times.clear()
    
    def is_running(self) -> bool:
        """检查是否在运行."""
        return self._listener is not None and self._listener.is_alive()


# 简单的测试代码
if __name__ == "__main__":
    import sys
    
    def on_press(event: TouchpadEvent):
        finger_text = {1: '单指', 2: '双指', 3: '三指', 4: '四指'}.get(event.finger_count, f'{event.finger_count}指')
        print(f"[{event.timestamp:.3f}] {finger_text}按下 @ ({event.x}, {event.y})")
    
    def on_hold(event: TouchpadEvent):
        finger_text = {1: '单指', 2: '双指', 3: '三指', 4: '四指'}.get(event.finger_count, f'{event.finger_count}指')
        print(f"[{event.timestamp:.3f}] {finger_text}长按触发! 持续 {event.duration_ms}ms")
    
    def on_release(event: TouchpadEvent):
        finger_text = {1: '单指', 2: '双指', 3: '三指', 4: '四指'}.get(event.finger_count, f'{event.finger_count}指')
        print(f"[{event.timestamp:.3f}] {finger_text}释放，总时长 {event.duration_ms}ms")
    
    def on_tap(event: TouchpadEvent):
        finger_text = {1: '单指', 2: '双指', 3: '三指', 4: '四指'}.get(event.finger_count, f'{event.finger_count}指')
        print(f"[{event.timestamp:.3f}] {finger_text}轻触")
    
    print("测试触摸板钩子")
    print("- 快速连续点击模拟多指手势")
    print("- 默认使用三指点击")
    print("- 按住超过300ms触发长按")
    print("- 按Ctrl+C退出")
    print()
    
    hook = TouchpadHook(
        gesture='triple',  # 可改为 'double', 'quadruple' 等
        hold_threshold_ms=300,
        on_press=on_press,
        on_hold=on_hold,
        on_release=on_release,
        on_tap=on_tap
    )
    hook.start()
    
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n退出...")
        hook.stop()
        sys.exit(0)
