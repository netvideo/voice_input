"""ASR WebSocket客户端模块 - 连接语音识别服务器."""

import asyncio
import base64
import json
import threading
import time
from typing import Optional, Callable, Dict, Any

import websockets
from websockets.exceptions import ConnectionClosed

from ime_input import SmartTextInput


class ASRClient:
    """
    ASR WebSocket客户端，实现流式语音识别协议.
    
    特性:
    - WebSocket连接管理
    - 自动重连
    - 心跳保活
    - 异步消息处理
    - 智能文本上屏（根据窗口类型自动选择最佳方式）
    """
    
    def __init__(
        self,
        ws_url: str,
        language: str = "zh-CN",
        enable_punctuation: bool = True,
        enable_itn: bool = True,
        on_result: Optional[Callable[[str, bool], None]] = None,
        on_error: Optional[Callable[[int, str], None]] = None,
        on_event: Optional[Callable[[str, Any], None]] = None,
        on_stats: Optional[Callable[[dict], None]] = None,
        auto_reconnect: bool = True,
        reconnect_interval: float = 3.0,
        enable_text_input: bool = True
    ):
        """初始化ASR客户端.
        
        Args:
            ws_url: WebSocket服务器地址
            language: 语言代码
            enable_punctuation: 是否启用标点
            enable_itn: 是否启用ITN数字转换
            on_result: 识别结果回调 (text, is_final)
            on_error: 错误回调 (code, message)
            on_event: 事件回调 (event_type, data)
            on_stats: 统计信息回调 (stats_dict)
            auto_reconnect: 是否自动重连
            reconnect_interval: 重连间隔（秒）
            enable_text_input: 是否启用文本上屏功能
        """
        self.ws_url = ws_url
        self.language = language
        self.enable_punctuation = enable_punctuation
        self.enable_itn = enable_itn
        self.on_result = on_result
        self.on_error = on_error
        self.on_event = on_event
        self.on_stats = on_stats
        self.auto_reconnect = auto_reconnect
        self.reconnect_interval = reconnect_interval
        self.enable_text_input = enable_text_input
        
        self._websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._is_connected = False
        self._is_recognizing = False
        self._seq = 0
        self._session_id: Optional[str] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        
        # 智能文本输入器
        self._text_input = SmartTextInput() if enable_text_input else None
        
        # 中间结果管理
        self._last_interim_text: str = ""
        
        # 录音时的心跳任务
        self._recording_heartbeat_task = None
    
    def start(self) -> bool:
        """启动客户端（在后台线程中运行事件循环）.
        
        Returns:
            是否成功启动
        """
        try:
            print(f"正在启动ASR客户端...")
            self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
            self._thread.start()
            print(f"后台线程已启动，等待连接...")
            
            timeout = 10.0
            start_time = time.time()
            check_count = 0
            while time.time() - start_time < timeout:
                if self._is_connected:
                    print(f"✓ 连接成功建立 (耗时 {time.time() - start_time:.1f}s)")
                    return True
                time.sleep(0.1)
                check_count += 1
                if check_count % 20 == 0:
                    print(f"  等待连接... ({time.time() - start_time:.1f}s/{timeout}s)")
            
            print(f"✗ 连接超时 ({timeout}s)")
            return False
            
        except Exception as e:
            print(f"启动客户端失败: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _run_event_loop(self):
        """在后台线程中运行事件循环."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._connect())
    
    async def _connect(self):
        """建立WebSocket连接."""
        while True:
            try:
                print(f"连接服务器: {self.ws_url}")
                print(f"尝试建立WebSocket连接...")
                
                async with websockets.connect(self.ws_url, ping_interval=10, ping_timeout=8) as websocket:
                    self._websocket = websocket
                    self._is_connected = True
                    print("✓ WebSocket连接成功")
                    
                    print("发送配置消息...")
                    await self._send_config()
                    print("✓ 配置已发送并确认")
                    
                    self._heartbeat_task = asyncio.create_task(self._heartbeat())
                    
                    await self._receive_loop()
                    
            except ConnectionClosed as e:
                print(f"连接关闭: {e}")
            except asyncio.TimeoutError:
                print(f"连接超时: 无法连接到 {self.ws_url}")
                print("请检查:")
                print("  1. 服务器是否已启动")
                print("  2. 服务器地址和端口是否正确")
                print("  3. 防火墙是否允许连接")
            except Exception as e:
                print(f"连接错误: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
            
            self._is_connected = False
            self._websocket = None
            
            if not self.auto_reconnect:
                break
            
            print(f"{self.reconnect_interval}秒后重连...")
            await asyncio.sleep(self.reconnect_interval)
    
    async def _send_config(self):
        """发送配置消息并等待确认."""
        config = {
            "type": "config",
            "data": {
                "sample_rate": 16000,
                "channels": 1,
                "sample_width": 2,
                "language": self.language,
                "enable_punctuation": self.enable_punctuation,
                "enable_itn": self.enable_itn,
                "vad_enabled": True,
                "vad_timeout_ms": 500
            }
        }
        
        await self._send_message(config)
        print("配置已发送")
        
        try:
            response = await asyncio.wait_for(
                self._websocket.recv(),
                timeout=3.0
            )
            data = json.loads(response)
            if data.get("type") == "event":
                print("服务器就绪")
            else:
                print(f"服务器响应: {data}")
        except asyncio.TimeoutError:
            print("警告: 等待服务器响应超时，但继续连接")
        except Exception as e:
            print(f"等待响应出错: {e}")
    
    async def _send_message(self, message: dict):
        """发送消息."""
        if self._websocket and self._is_connected:
            try:
                await self._websocket.send(json.dumps(message))
            except Exception as e:
                print(f"发送消息失败: {e}")
    
    async def _send_ping(self):
        """发送心跳（用于长时间录音时保持连接）."""
        try:
            if self._websocket:
                await self._websocket.ping()
        except Exception as e:
            print(f"发送心跳失败: {e}")
    
    def send_audio(self, audio_data: bytes):
        """发送音频数据（线程安全）."""
        if not self._is_connected or not self._is_recognizing:
            return
        
        message = {
            "type": "audio",
            "seq": self._seq,
            "is_final": False,
            "data": base64.b64encode(audio_data).decode('utf-8')
        }
        
        self._seq += 1
        
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._send_message(message),
                self._loop
            )
    
    def send_end(self):
        """发送结束消息."""
        if not self._is_connected:
            return
        
        self._is_recognizing = False
        
        message = {
            "type": "end",
            "seq": self._seq
        }
        
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._send_message(message),
                self._loop
            )
        
        print("结束消息已发送")
    
    async def _receive_loop(self):
        """接收消息循环."""
        try:
            async for message in self._websocket:
                await self._handle_message(message)
        except ConnectionClosed:
            pass
        except Exception as e:
            print(f"接收消息错误: {e}")
    
    async def _handle_message(self, message: str):
        """处理接收到的消息."""
        print(f"[原始消息] {message}")
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "result":
                self._handle_result(data)
            elif msg_type == "event":
                self._handle_event(data)
            elif msg_type == "error":
                self._handle_error(data)
            else:
                print(f"未知消息类型: {msg_type}")
                
        except json.JSONDecodeError:
            print(f"无效的JSON消息: {message}")
        except Exception as e:
            print(f"处理消息错误: {e}")
    
    def _handle_result(self, data: dict):
        """处理识别结果."""
        code = data.get("code", 0)
        if code != 0:
            print(f"识别错误: {data.get('message')}")
            return
        
        result_data = data.get("data", {})
        text = result_data.get("text", "")
        is_final = result_data.get("is_final", False)
        confidence = result_data.get("confidence", 0.0)
        
        # 打印统计信息（仅最终结果）
        if is_final:
            stats = data.get("stats", {})
            audio_duration = stats.get("audio_duration", 0)
            session_duration = stats.get("duration", 0)
            print(f"\n[统计] 音频: {audio_duration:.2f}s, 会话: {session_duration:.2f}s")
        
        if text:
            # 打印识别结果（多行显示，避免被截断）
            prefix = f"识别结果{'(最终)' if is_final else '(中间)'}: "
            if len(text) > 200:
                print(prefix)
                for i in range(0, len(text), 200):
                    print(f"  {text[i:i+200]}")
                print(f"  (置信度: {confidence:.2f})")
            else:
                print(f"{prefix}{text} (置信度: {confidence:.2f})")
            
            # 只在最终结果时上屏
            if is_final and self.enable_text_input and self._text_input:
                # 删除之前的中间结果
                if self._last_interim_text:
                    self._text_input.send_backspace(len(self._last_interim_text))
                    time.sleep(0.03)
                # 上屏最终结果
                self._text_input.send_text(text)
                self._last_interim_text = ""
            
            if self.on_result:
                self.on_result(text, is_final)
    
    def _handle_event(self, data: dict):
        """处理事件消息."""
        event_type = data.get("event_type")
        timestamp = data.get("timestamp_ms", 0)
        
        print(f"事件: {event_type} @ {timestamp}ms")
        
        if self.on_event:
            self.on_event(event_type, data)
    
    def _handle_error(self, data: dict):
        """处理错误消息."""
        code = data.get("code", -1)
        message = data.get("message", "Unknown error")
        
        print(f"服务器错误 [{code}]: {message}")
        
        if self.on_error:
            self.on_error(code, message)
    
    async def _heartbeat(self):
        """心跳保活."""
        while self._is_connected:
            try:
                if self._websocket:
                    await self._websocket.ping()
                await asyncio.sleep(60)  # 改为60秒，与服务器匹配
            except Exception as e:
                print(f"心跳错误: {e}")
                break
    
    def start_recognition(self):
        """开始识别."""
        self._is_recognizing = True
        self._seq = 0
        self._last_interim_text = ""
        print("开始识别会话")
        
        # 启动录音时的心跳任务（每5秒发送一次）
        if self._loop:
            self._recording_heartbeat_task = asyncio.run_coroutine_threadsafe(
                self._recording_heartbeat(),
                self._loop
            )
    
    async def _recording_heartbeat(self):
        """录音期间的心跳任务."""
        while self._is_recognizing:
            try:
                if self._websocket:
                    await self._websocket.ping()
                await asyncio.sleep(5)
            except Exception as e:
                print(f"录音心跳错误: {e}")
                break
    
    def stop_recognition(self):
        """停止识别."""
        # 停止录音心跳任务
        if self._recording_heartbeat_task:
            self._recording_heartbeat_task.cancel()
            self._recording_heartbeat_task = None
        
        self.send_end()
        print("停止识别会话")
    
    def stop(self):
        """停止客户端."""
        self.auto_reconnect = False
        self._is_recognizing = False
        
        # 停止所有心跳任务
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._recording_heartbeat_task:
            self._recording_heartbeat_task.cancel()
        
        if self._websocket:
            asyncio.run_coroutine_threadsafe(
                self._websocket.close(),
                self._loop
            )
        
        if self._loop:
            self._loop.stop()
        
        print("客户端已停止")
    
    def is_connected(self) -> bool:
        """检查是否已连接."""
        return self._is_connected
    
    def is_recognizing(self) -> bool:
        """检查是否正在识别."""
        return self._is_recognizing


# 测试代码
if __name__ == "__main__":
    import time
    
    def on_result(text: str, is_final: bool):
        print(f"[回调] {'最终' if is_final else '中间'}结果: {text}")
    
    def on_error(code: int, message: str):
        print(f"[回调] 错误 [{code}]: {message}")
    
    def on_event(event_type: str, data: Any):
        print(f"[回调] 事件: {event_type}")
    
    WS_URL = "wss://your-asr-server.com/asr/v1/stream"
    
    print("测试ASR客户端（智能上屏版）")
    print(f"服务器: {WS_URL}")
    print()
    
    client = ASRClient(
        ws_url=WS_URL,
        on_result=on_result,
        on_error=on_error,
        on_event=on_event,
        enable_text_input=True
    )
    
    if client.start():
        print("客户端启动成功")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n用户中断")
    else:
        print("客户端启动失败")
    
    client.stop()
