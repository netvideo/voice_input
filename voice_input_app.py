"""Windows语音输入客户端主程序.

功能:
- 支持多种触发方式（鼠标中键/侧键、CAPS LOCK等）
- 录音并实时识别
- 将结果上屏到活动窗口

使用方法:
1. 按住配置的触发键超过阈值时间开始录音
2. 说话...
3. 释放触发键停止录音
4. 识别结果自动上屏

配置:
- 编辑 config.ini 修改触发方式和服务器地址
"""

import configparser
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional, Union

# 将当前目录添加到路径
sys.path.insert(0, str(Path(__file__).parent))

from audio_capture import AudioCapture
from asr_client import ASRClient
from ali_asr_client import AliASRClient
from keyboard_hook import KeyboardEvent, KeyboardHook
from mouse_hook import MouseEvent, MouseHook
from text_input import TextInput
from touchpad_hook import TouchpadEvent, TouchpadHook


class VoiceInputApp:
    """语音输入应用主类."""
    
    DEFAULT_CONFIG = {
        'server': {
            'provider': 'local',  # local: 本地ASR, ali: 阿里云
            'ws_url': 'ws://127.0.0.1:8765',
            'language': 'zh-CN',
            'enable_punctuation': 'true',
            'enable_itn': 'true',
            # 阿里云配置
            'ali_token': '',
            'ali_appkey': '',
            'ali_gateway': 'wss://nls-gateway-cn-shanghai.aliyuncs.com/ws/v1',
        },
        'trigger': {
            'type': 'mouse',  # 可选: mouse, keyboard, touchpad
            'button': 'middle',  # mouse: middle, x1, x2, left, right; keyboard: caps_lock, ctrl_l, ctrl_r, alt_l, alt_r, shift_l, shift_r, f1-f12; touchpad: single, double, triple, quadruple, edge_swipe
            'hold_threshold_ms': '500',
        },
        'touchpad': {
            'gesture': 'triple',
            'edge_swipe_enabled': 'false',
            'edge_swipe_width': '50',
            'hold_threshold_ms': '300',
        },
        'input': {
            'use_clipboard': 'true',
            'show_intermediate': 'false',
        },
        'audio': {
            'chunk_duration_ms': '100',
        }
    }
    
    def __init__(self):
        """初始化应用."""
        self.config = self._load_config()
        
        # 组件
        self.mouse_hook: Optional[MouseHook] = None
        self.keyboard_hook: Optional[KeyboardHook] = None
        self.touchpad_hook: Optional[TouchpadHook] = None
        self.audio_capture: Optional[AudioCapture] = None
        self.asr_client: Optional[ASRClient] = None
        self.text_input: Optional[TextInput] = None
        
        # 状态
        self.is_recording = False
        self.is_connected = False
        self.accumulated_text = ""
        self._lock = threading.Lock()
        
        # 运行标志
        self._running = False
        
        # 触发方式
        self.trigger_type = self.config.get('trigger', 'type')
        self.trigger_button = self.config.get('trigger', 'button')
    
    def _load_config(self) -> configparser.ConfigParser:
        """加载配置文件.
        
        Returns:
            配置解析器
        """
        config = configparser.ConfigParser()
        
        # 设置默认值
        config.read_dict(self.DEFAULT_CONFIG)
        
        # 尝试读取配置文件
        config_path = Path(__file__).parent / "config.ini"
        if config_path.exists():
            config.read(config_path, encoding='utf-8')
            print(f"加载配置: {config_path}")
        else:
            print("使用默认配置")
            # 创建默认配置文件
            self._create_default_config(config_path, config)
        
        return config
    
    def _create_default_config(self, config_path: Path, config: configparser.ConfigParser):
        """创建默认配置文件.
        
        Args:
            config_path: 配置文件路径
            config: 配置解析器
        """
        with open(config_path, 'w', encoding='utf-8') as f:
            config.write(f)
        
        print(f"创建默认配置: {config_path}")
    
    def _on_trigger_press(self, event: Union[MouseEvent, KeyboardEvent, TouchpadEvent]):
        """处理触发键按下事件.
        
        Args:
            event: 事件数据
        """
        if isinstance(event, MouseEvent):
            print(f"{event.button} 按下 @ ({event.x}, {event.y}) - 准备录音")
        elif isinstance(event, TouchpadEvent):
            finger_text = {1: '单指', 2: '双指', 3: '三指', 4: '四指'}.get(event.finger_count, f'{event.finger_count}指')
            print(f"触摸板{finger_text}按下 @ ({event.x}, {event.y}) - 准备录音")
        elif isinstance(event, KeyboardEvent):
            key_name = self._get_key_display_name(event.key)
            print(f"{key_name} 按下 - 准备录音")
    
    def _on_trigger_hold(self, event: Union[MouseEvent, KeyboardEvent, TouchpadEvent]):
        """处理触发键长按事件（开始录音）.
        
        Args:
            event: 事件数据
        """
        if isinstance(event, MouseEvent):
            print(f"{event.button} 长按 {event.duration_ms}ms @ ({event.x}, {event.y}) - 开始录音")
        elif isinstance(event, TouchpadEvent):
            finger_text = {1: '单指', 2: '双指', 3: '三指', 4: '四指'}.get(event.finger_count, f'{event.finger_count}指')
            print(f"触摸板{finger_text}长按 {event.duration_ms}ms @ ({event.x}, {event.y}) - 开始录音")
        elif isinstance(event, KeyboardEvent):
            key_name = self._get_key_display_name(event.key)
            print(f"{key_name} 长按 {event.duration_ms}ms - 开始录音")
        
        with self._lock:
            if not self.is_recording:
                self._start_recording()
    
    def _on_trigger_release(self, event: Union[MouseEvent, KeyboardEvent, TouchpadEvent]):
        """处理触发键释放事件（停止录音）.
        
        Args:
            event: 事件数据
        """
        if isinstance(event, MouseEvent):
            print(f"{event.button} 释放 @ ({event.x}, {event.y}) - 停止录音（总时长 {event.duration_ms}ms）")
        elif isinstance(event, TouchpadEvent):
            finger_text = {1: '单指', 2: '双指', 3: '三指', 4: '四指'}.get(event.finger_count, f'{event.finger_count}指')
            print(f"触摸板{finger_text}释放 @ ({event.x}, {event.y}) - 停止录音（总时长 {event.duration_ms}ms）")
        elif isinstance(event, KeyboardEvent):
            key_name = self._get_key_display_name(event.key)
            print(f"{key_name} 释放 - 停止录音（总时长 {event.duration_ms}ms）")
        else:
            print(f"CAPS LOCK 释放 - 停止录音（总时长 {event.duration_ms}ms）")
        
        with self._lock:
            if self.is_recording:
                self._stop_recording()
    
    def _start_recording(self):
        """开始录音."""
        if not self.asr_client or not self.asr_client.is_connected():
            print("错误: ASR客户端未连接")
            return
        
        self.is_recording = True
        self.accumulated_text = ""
        
        # 开始音频采集
        if self.audio_capture:
            self.audio_capture.start()
        
        # 开始ASR识别会话
        if self.asr_client:
            self.asr_client.start_recognition()
        
        print("🎤 录音中...")
    
    def _stop_recording(self):
        """停止录音."""
        self.is_recording = False
        
        # 停止音频采集
        if self.audio_capture:
            self.audio_capture.stop()
        
        # 停止ASR识别会话
        if self.asr_client:
            self.asr_client.stop_recognition()
        
        print("⏹️ 录音停止，等待识别结果...")
    
    def _on_audio_chunk(self, audio_data: bytes):
        """处理音频数据块.
        
        Args:
            audio_data: PCM音频数据
        """
        if self.is_recording and self.asr_client:
            self.asr_client.send_audio(audio_data)
    
    def _on_asr_result(self, text: str, is_final: bool):
        """处理ASR识别结果.
        
        Args:
            text: 识别文本
            is_final: 是否为最终结果
        """
        show_intermediate = self.config.getboolean('input', 'show_intermediate')
        
        if is_final:
            # 最终结果
            print(f"✅ 最终结果: {text}")
            
            # 上屏到活动窗口
            if text and self.text_input:
                self.text_input.send_text(
                    text, 
                    use_clipboard=self.config.getboolean('input', 'use_clipboard')
                )
        else:
            # 中间结果 - 实时上屏
            if show_intermediate and text and self.text_input:
                print(f"⏳ 中间结果: {text}")
                # 实时上屏中间结果（可选：添加\r覆盖模式）
                self.text_input.send_text(
                    text,
                    use_clipboard=self.config.getboolean('input', 'use_clipboard')
                )
    
    def _on_asr_error(self, code: int, message: str):
        """处理ASR错误.
        
        Args:
            code: 错误码
            message: 错误消息
        """
        print(f"❌ ASR错误 [{code}]: {message}")
    
    def _on_asr_event(self, event_type: str, data: dict):
        """处理ASR事件.
        
        Args:
            event_type: 事件类型
            data: 事件数据
        """
        if event_type == 'speech_start':
            print("检测到语音开始")
        elif event_type == 'speech_end':
            print("检测到语音结束")
    
    def _init_trigger(self):
        """初始化触发方式."""
        threshold_ms = self.config.getint('trigger', 'hold_threshold_ms')
        print(f"长按阈值: {threshold_ms}ms")
        
        if self.trigger_type == 'mouse':
            # 鼠标触发
            button = self.config.get('trigger', 'button')
            print(f"触发方式: 鼠标 {button}")
            
            self.mouse_hook = MouseHook(
                trigger_button=button,
                hold_threshold_ms=threshold_ms,
                on_press=self._on_trigger_press,
                on_hold=self._on_trigger_hold,
                on_release=self._on_trigger_release
            )
            self.mouse_hook.start()
            print(f"✅ 鼠标监听已启动（{button}键）")
            
        elif self.trigger_type == 'keyboard':
            # 键盘触发
            supported_keys = ['caps_lock', 'ctrl', 'ctrl_l', 'ctrl_r', 'alt', 'alt_l', 'alt_r', 
                            'shift', 'shift_l', 'shift_r', 'f1', 'f2', 'f3', 'f4', 'f5', 
                            'f6', 'f7', 'f8', 'f9', 'f10', 'f11', 'f12']
            
            if self.trigger_button in supported_keys:
                key_display_names = {
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
                }
                key_name = key_display_names.get(self.trigger_button, self.trigger_button.upper())
                print(f"触发方式: 键盘 {key_name}")
                
                self.keyboard_hook = KeyboardHook(
                    trigger_key=self.trigger_button,
                    hold_threshold_ms=threshold_ms,
                    on_press=self._on_trigger_press,
                    on_hold=self._on_trigger_hold,
                    on_release=self._on_trigger_release
                )
                self.keyboard_hook.start()
                print(f"✅ 键盘监听已启动（{key_name}）")
            else:
                raise ValueError(f"不支持的键盘按键: {self.trigger_button}. 支持: {supported_keys}")
                
        elif self.trigger_type == 'touchpad':
            # 触摸板触发
            gesture = self.config.get('touchpad', 'gesture', fallback='triple')
            tp_threshold_ms = self.config.getint('touchpad', 'hold_threshold_ms', fallback=300)
            edge_swipe_enabled = self.config.getboolean('touchpad', 'edge_swipe_enabled', fallback=False)
            edge_swipe_width = self.config.getint('touchpad', 'edge_swipe_width', fallback=50)
            
            gesture_name = {
                'single': '单指',
                'double': '双指',
                'triple': '三指',
                'quadruple': '四指',
                'edge_swipe': '边缘轻扫',
            }.get(gesture, gesture)
            
            print(f"触发方式: 触摸板 {gesture_name}")
            
            self.touchpad_hook = TouchpadHook(
                gesture=gesture,
                hold_threshold_ms=tp_threshold_ms,
                edge_swipe_enabled=edge_swipe_enabled,
                edge_swipe_width=edge_swipe_width,
                on_press=self._on_trigger_press,
                on_hold=self._on_trigger_hold,
                on_release=self._on_trigger_release
            )
            self.touchpad_hook.start()
            print(f"✅ 触摸板监听已启动（{gesture_name}）")
        else:
            raise ValueError(f"不支持的触发类型: {self.trigger_type}")
    
    def start(self) -> bool:
        """启动应用.
        
        Returns:
            是否成功启动
        """
        print("=" * 50)
        print("Windows语音输入客户端")
        print("=" * 50)
        print()
        
        # 初始化文本输入
        self.text_input = TextInput()
        
        # 初始化音频采集
        self.audio_capture = AudioCapture(
            on_audio_chunk=self._on_audio_chunk
        )
        
        # 初始化ASR客户端
        provider = self.config.get('server', 'provider', fallback='local')
        
        if provider == 'ali':
            # 阿里云智能语音交互
            ali_token = self.config.get('server', 'ali_token', fallback='')
            ali_appkey = self.config.get('server', 'ali_appkey', fallback='')
            ali_gateway = self.config.get('server', 'ali_gateway', fallback='wss://nls-gateway-cn-shanghai.aliyuncs.com/ws/v1')
            
            if not ali_token or not ali_appkey:
                print("错误: 使用阿里云ASR需要配置 ali_token 和 ali_appkey")
                print("请在 config.ini 的 [server] 部分配置:")
                print("  ali_token = 你的Token")
                print("  ali_appkey = 你的Appkey")
                return False
            
            print(f"使用阿里云智能语音交互服务")
            print(f"  Appkey: {ali_appkey}")
            print(f"  网关: {ali_gateway}")
            
            self.asr_client = AliASRClient(
                token=ali_token,
                appkey=ali_appkey,
                gateway=ali_gateway,
                enable_intermediate_result=True,
                enable_punctuation=self.config.getboolean('server', 'enable_punctuation'),
                enable_itn=self.config.getboolean('server', 'enable_itn'),
                on_result=self._on_asr_result,
                on_event=self._on_asr_event,
                on_error=self._on_asr_error,
            )
        else:
            # 本地ASR服务器
            ws_url = self.config.get('server', 'ws_url')
            print(f"连接本地ASR服务器: {ws_url}")
            
            self.asr_client = ASRClient(
                ws_url=ws_url,
                language=self.config.get('server', 'language'),
                enable_punctuation=self.config.getboolean('server', 'enable_punctuation'),
                enable_itn=self.config.getboolean('server', 'enable_itn'),
                on_result=self._on_asr_result,
                on_error=self._on_asr_error,
                on_event=self._on_asr_event,
                auto_reconnect=True
            )
        
        if not self.asr_client.start():
            print("错误: 无法连接到ASR服务器")
            if provider == 'ali':
                print("请检查:")
                print("  1. ali_token 是否正确")
                print("  2. ali_appkey 是否正确")
                print("  3. 网络连接是否正常")
            else:
                print("请检查:")
                print("  1. 服务器地址是否正确")
                print("  2. 网络连接是否正常")
                print("  3. 服务器是否运行")
            return False
        
        self.is_connected = True
        print("✅ 已连接到ASR服务器")
        print()
        
        # 初始化触发方式
        try:
            self._init_trigger()
        except Exception as e:
            print(f"错误: 初始化触发方式失败: {e}")
            return False
        
        print()
        
        self._running = True
        
        # 获取阈值
        threshold_ms = self.config.getint('trigger', 'hold_threshold_ms')
        
        # 打印使用说明
        if self.trigger_type == 'mouse':
            button_name = {
                'middle': '鼠标中键（滚轮按下）',
                'x1': '鼠标侧键-后退',
                'x2': '鼠标侧键-前进',
                'left': '鼠标左键',
                'right': '鼠标右键',
            }.get(self.trigger_button, self.trigger_button)
            
            print("使用说明:")
            print(f"- 按住 {button_name} 超过{threshold_ms}ms开始录音")
            print("- 说话...")
            print(f"- 释放 {button_name} 停止录音并上屏")
        elif self.trigger_type == 'touchpad':
            gesture = self.config.get('touchpad', 'gesture', fallback='triple')
            tp_threshold_ms = self.config.getint('touchpad', 'hold_threshold_ms', fallback=300)
            
            gesture_name = {
                'single': '单指点击',
                'double': '双指点击',
                'triple': '三指点击',
                'quadruple': '四指点击',
                'edge_swipe': '边缘轻扫',
            }.get(gesture, gesture)
            
            print("使用说明:")
            print(f"- 使用 {gesture_name} 触摸板超过{tp_threshold_ms}ms开始录音")
            print("- 说话...")
            print(f"- 释放触摸板停止录音并上屏")
            print("  提示: 快速连续点击可模拟多指手势")
        elif self.trigger_type == 'keyboard':
            key_name = self._get_key_display_name(self.trigger_button)
            print("使用说明:")
            print(f"- 按住 {key_name} 超过{threshold_ms}ms开始录音")
            print("- 说话...")
            print(f"- 释放 {key_name} 停止录音并上屏")
        
        print("- 按 Ctrl+C 退出")
        print()
        
        return True
    
    def stop(self):
        """停止应用."""
        print("\n正在停止...")
        self._running = False
        
        # 停止触发钩子
        if self.mouse_hook:
            self.mouse_hook.stop()
        if self.keyboard_hook:
            self.keyboard_hook.stop()
        if self.touchpad_hook:
            self.touchpad_hook.stop()
        
        # 停止录音
        if self.is_recording:
            self._stop_recording()
        
        # 停止ASR客户端
        if self.asr_client:
            self.asr_client.stop()
        
        print("已停止")
    
    def _get_key_display_name(self, key: str) -> str:
        """获取按键的显示名称.
        
        Args:
            key: 按键代码
            
        Returns:
            显示名称
        """
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
        return display_names.get(key, key.upper())
    
    def run(self):
        """运行主循环."""
        try:
            while self._running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n用户中断")
        finally:
            self.stop()


def main():
    """主函数."""
    app = VoiceInputApp()
    
    if app.start():
        app.run()
    else:
        print("\n启动失败，请检查配置")
        sys.exit(1)


if __name__ == "__main__":
    main()
