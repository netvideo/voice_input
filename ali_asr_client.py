"""阿里云智能语音交互 WebSocket API 客户端.

文档: https://help.aliyun.com/zh/isi/developer-reference/websocket

特性:
- 支持实时语音识别
- 支持长语音
- 支持中间结果、标点、ITN
- 支持热词
"""

import asyncio
import base64
import json
import os
import random
import string
import threading
import time
import uuid
from typing import Optional, Callable, Dict, Any

import websockets
from websockets.exceptions import ConnectionClosed


def generate_message_id() -> str:
    """生成32位唯一消息ID."""
    return uuid.uuid4().hex


def generate_task_id() -> str:
    """生成32位唯一任务ID."""
    return uuid.uuid4().hex


class AliASRClient:
    """阿里云智能语音交互 WebSocket 客户端.
    
    使用方式:
        client = AliASRClient(
            token="your_token",
            appkey="your_appkey",
            on_result=callback
        )
        client.start()
        # 发送音频...
        client.stop()
    """
    
    # 默认网关地址
    DEFAULT_GATEWAY = "wss://nls-gateway-cn-shanghai.aliyuncs.com/ws/v1"
    
    def __init__(
        self,
        token: str,
        appkey: str,
        gateway: str = None,
        format: str = "PCM",  # PCM, WAV, OPUS, SPEEX, AMR, MP3, AAC
        sample_rate: int = 16000,
        enable_intermediate_result: bool = True,
        enable_punctuation: bool = True,
        enable_itn: bool = True,
        vocabulary_id: str = None,
        on_result: Optional[Callable[[str, bool], None]] = None,
        on_event: Optional[Callable[[str, Dict], None]] = None,
        on_error: Optional[Callable[[int, str], None]] = None,
    ):
        """初始化阿里ASR客户端.
        
        Args:
            token: 阿里云访问Token
            appkey: 项目Appkey
            gateway: 网关地址
            format: 音频格式 (PCM/WAV/OPUS/SPEEX/AMR/MP3/AAC)
            sample_rate: 采样率 (8000/16000)
            enable_intermediate_result: 是否返回中间结果
            enable_punctuation: 是否添加标点
            enable_itn: 是否启用ITN (中文数字转阿拉伯数字)
            vocabulary_id: 热词ID
            on_result: 结果回调 (text, is_final)
            on_event: 事件回调
            on_error: 错误回调
        """
        self.token = token
        self.appkey = appkey
        self.gateway = gateway or self.DEFAULT_GATEWAY
        self.format = format
        self.sample_rate = sample_rate
        self.enable_intermediate_result = enable_intermediate_result
        self.enable_punctuation = enable_punctuation
        self.enable_itn = enable_itn
        self.vocabulary_id = vocabulary_id
        
        self.on_result = on_result
        self.on_event = on_event
        self.on_error = on_error
        
        self._websocket = None
        self._is_started = False
        self._task_id = None
        self._loop = None
        self._thread = None
        self._receive_task = None
        self._lock = threading.Lock()
    
    def _get_url(self) -> str:
        """获取WebSocket连接URL."""
        return f"{self.gateway}?token={self.token}"
    
    def _build_start_command(self) -> Dict:
        """构建开始识别命令."""
        self._task_id = generate_task_id()
        
        payload = {
            "format": self.format,
            "sample_rate": self.sample_rate,
            "enable_intermediate_result": self.enable_intermediate_result,
            "enable_punctuation_prediction": self.enable_punctuation,
            "enable_inverse_text_normalization": self.enable_itn,
        }
        
        if self.vocabulary_id:
            payload["vocabulary_id"] = self.vocabulary_id
        
        return {
            "header": {
                "message_id": generate_message_id(),
                "task_id": self._task_id,
                "namespace": "SpeechTranscriber",
                "name": "StartTranscription",
                "appkey": self.appkey
            },
            "payload": payload
        }
    
    def _build_stop_command(self) -> Dict:
        """构建停止识别命令."""
        return {
            "header": {
                "message_id": generate_message_id(),
                "task_id": self._task_id,
                "namespace": "SpeechTranscriber",
                "name": "StopTranscription",
                "appkey": self.appkey
            }
        }
    
    def start(self) -> bool:
        """启动客户端."""
        if self._is_started:
            return True
        
        try:
            self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
            self._thread.start()
            
            # 等待连接
            timeout = 10.0
            start_time = time.time()
            while time.time() - start_time < timeout:
                if self._websocket:
                    return True
                time.sleep(0.1)
            
            return False
            
        except Exception as e:
            print(f"启动失败: {e}")
            return False
    
    def _run_event_loop(self):
        """运行事件循环."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._connect())
    
    async def _connect(self):
        """连接到服务器."""
        while True:
            try:
                url = self._get_url()
                print(f"连接到: {url[:50]}...")
                
                async with websockets.connect(url) as ws:
                    self._websocket = ws
                    print("连接成功")
                    
                    # 发送开始命令
                    start_cmd = self._build_start_command()
                    await ws.send(json.dumps(start_cmd))
                    print(f"已发送开始命令: {start_cmd['header']['task_id']}")
                    
                    # 接收消息
                    await self._receive_loop()
                    
            except ConnectionClosed as e:
                print(f"连接关闭: {e}")
            except Exception as e:
                print(f"连接错误: {e}")
            
            self._websocket = None
            await asyncio.sleep(1.0)
    
    async def _receive_loop(self):
        """接收消息循环."""
        try:
            async for message in self._websocket:
                await self._handle_message(message)
        except Exception as e:
            print(f"接收错误: {e}")
    
    async def _handle_message(self, message: str):
        """处理服务器消息."""
        try:
            data = json.loads(message)
            header = data.get("header", {})
            name = header.get("name", "")
            status = header.get("status", 0)
            
            # 触发事件回调
            if self.on_event:
                self.on_event(name, data)
            
            if name == "TranscriptionStarted":
                print("[事件] 识别已开始")
                self._is_started = True
            
            elif name == "TranscriptionResultChanged":
                # 中间结果
                payload = data.get("payload", {})
                text = payload.get("result", "")
                index = payload.get("index", 0)
                print(f"[中间结果 {index}] {text}")
                
                if self.on_result:
                    self.on_result(text, False)
            
            elif name == "SentenceEnd":
                # 句子结束
                payload = data.get("payload", {})
                text = payload.get("result", "")
                index = payload.get("index", 0)
                print(f"[最终结果 {index}] {text}")
                
                if self.on_result:
                    self.on_result(text, True)
            
            elif name == "TranscriptionCompleted":
                print("[事件] 识别已完成")
                self._is_started = False
            
            elif status >= 40000000:
                # 错误
                msg = header.get("status_message", "Unknown error")
                print(f"[错误] {status}: {msg}")
                if self.on_error:
                    self.on_error(status, msg)
        
        except json.JSONDecodeError:
            print(f"JSON解析错误: {message[:100]}")
        except Exception as e:
            print(f"处理消息错误: {e}")
    
    def send_audio(self, audio_data: bytes):
        """发送音频数据 (线程安全).
        
        Args:
            audio_data: PCM音频数据
        """
        if not self._websocket or not self._is_started:
            return
        
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._send_audio_async(audio_data),
                self._loop
            )
    
    async def _send_audio_async(self, audio_data: bytes):
        """异步发送音频."""
        try:
            # 阿里云使用二进制帧发送音频
            await self._websocket.send(audio_data)
        except Exception as e:
            print(f"发送音频错误: {e}")
    
    def stop(self):
        """停止识别."""
        if not self._websocket or not self._is_started:
            return
        
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._send_stop_async(),
                self._loop
            )
        
        self._is_started = False
    
    async def _send_stop_async(self):
        """异步发送停止命令."""
        try:
            stop_cmd = self._build_stop_command()
            await self._websocket.send(json.dumps(stop_cmd))
            print("已发送停止命令")
        except Exception as e:
            print(f"发送停止命令错误: {e}")


def get_token(access_key_id: str, access_key_secret: str) -> str:
    """获取阿里云访问Token.
    
    需要安装 aliyun-python-sdk-core:
        pip install aliyun-python-sdk-core
    
    Args:
        access_key_id: AccessKey ID
        access_key_secret: AccessKey Secret
        
    Returns:
        Token字符串
    """
    try:
        from aliyunsdkcore.client import AcsClient
        from aliyunsdkcore.request import CommonRequest
        
        client = AcsClient(access_key_id, access_key_secret, 'cn-shanghai')
        
        request = CommonRequest()
        request.set_method('POST')
        request.set_domain('nls-meta.cn-shanghai.aliyuncs.com')
        request.set_version('2019-02-28')
        request.set_action_name('CreateToken')
        
        response = client.do_action_with_exception(request)
        data = json.loads(response)
        
        token = data.get('Token', {}).get('Id')
        print(f"获取Token成功: {token[:20]}...")
        return token
        
    except ImportError:
        print("请安装阿里云SDK: pip install aliyun-python-sdk-core")
        raise
    except Exception as e:
        print(f"获取Token失败: {e}")
        raise


# 测试
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="阿里云ASR客户端测试")
    parser.add_argument("--token", required=True, help="访问Token")
    parser.add_argument("--appkey", required=True, help="项目Appkey")
    parser.add_argument("--file", help="音频文件路径 (WAV)")
    parser.add_argument("--url", default="wss://nls-gateway-cn-shanghai.aliyuncs.com/ws/v1", help="网关地址")
    
    args = parser.parse_args()
    
    results = []
    
    def on_result(text: str, is_final: bool):
        print(f"结果 [{'最终' if is_final else '中间'}]: {text}")
        if is_final:
            results.append(text)
    
    def on_event(event: str, data: Dict):
        print(f"事件: {event}")
    
    def on_error(code: int, msg: str):
        print(f"错误: {code} - {msg}")
    
    client = AliASRClient(
        token=args.token,
        appkey=args.appkey,
        gateway=args.url,
        enable_intermediate_result=True,
        enable_punctuation=True,
        enable_itn=True,
        on_result=on_result,
        on_event=on_event,
        on_error=on_error
    )
    
    if client.start():
        print("客户端已启动")
        
        if args.file:
            # 从文件发送
            import wave
            
            with wave.open(args.file, "rb") as wf:
                # 读取音频
                frames = wf.readframes(wf.getnframes())
                
                # 发送
                chunk_size = 3200  # 100ms @ 16kHz
                for i in range(0, len(frames), chunk_size):
                    chunk = frames[i:i+chunk_size]
                    client.send_audio(chunk)
                    time.sleep(0.1)
                
                # 停止
                time.sleep(1)
                client.stop()
        
        else:
            print("请发送音频数据或使用 --file 参数")
            print("按 Ctrl+C 退出")
            
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                client.stop()
    
    print("\n最终结果:")
    print("".join(results))
