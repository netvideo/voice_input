"""ASR服务端测试程序.

功能:
- 模拟ASR WebSocket服务器
- 支持流式音频接收
- 模拟识别延迟和结果返回
- 提供测试模式和调试信息
- 支持多种测试场景

使用方法:
    python asr_server_test.py

可选参数:
    --host: 监听地址 (默认: 0.0.0.0)
    --port: 监听端口 (默认: 8765)
    --mode: 测试模式 (echo/delay/random/error)
    --delay: 模拟延迟 (毫秒)
"""

import argparse
import asyncio
import base64
import json
import random
import time
import wave
from pathlib import Path
from typing import Dict, Optional, Set

import websockets



class MockASRServer:
    """模拟ASR服务器."""
    
    # 测试用的模拟识别文本
    MOCK_TEXTS = [
        "你好",
        "你好世界",
        "今天天气不错",
        "这是一个测试",
        "语音识别测试成功",
        "感谢使用语音输入",
        "请继续说话",
        "识别中请稍候",
    ]
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        mode: str = "random",
        delay_ms: int = 500
    ):
        """初始化测试服务器.
        
        Args:
            host: 监听地址
            port: 监听端口
            mode: 测试模式 (echo/delay/random/error)
            delay_ms: 模拟延迟（毫秒）
        """
        self.host = host
        self.port = port
        self.mode = mode
        self.delay_ms = delay_ms / 1000.0  # 转换为秒
        
        # 连接管理
        self.connections: Set = set()
        self.session_counter = 0
        
        # 统计信息
        self.stats = {
            'total_connections': 0,
            'active_connections': 0,
            'total_audio_chunks': 0,
            'total_duration_ms': 0,
        }
        
        # 保存音频数据（用于调试）
        self.save_audio = True
        self.audio_buffer: Dict[str, list] = {}
    
    async def handle_client(self, websocket):
        """处理客户端连接.
        
        Args:
            websocket: WebSocket连接
        """
        client_id = f"client_{id(websocket)}"
        session_id = f"session_{self.session_counter:06d}"
        self.session_counter += 1
        
        self.connections.add(websocket)
        self.stats['total_connections'] += 1
        self.stats['active_connections'] = len(self.connections)
        
        # 获取请求路径（兼容新版本websockets）
        try:
            path = websocket.request.path if hasattr(websocket, 'request') else '/'
        except:
            path = '/'
        
        print(f"\n[+] 新连接: {client_id} (Session: {session_id})")
        print(f"    当前连接数: {self.stats['active_connections']}")
        
        # 初始化音频缓冲区
        self.audio_buffer[session_id] = []
        
        try:
            async for message in websocket:
                await self._process_message(websocket, message, session_id)
                
        except websockets.exceptions.ConnectionClosed as e:
            print(f"[-] 连接关闭: {client_id} (Code: {e.code})")
        except Exception as e:
            print(f"[!] 错误: {client_id} - {e}")
        finally:
            self.connections.discard(websocket)
            self.stats['active_connections'] = len(self.connections)
            
            # 保存音频文件
            if self.save_audio and self.audio_buffer.get(session_id):
                self._save_audio(session_id)
            
            # 清理缓冲区
            if session_id in self.audio_buffer:
                del self.audio_buffer[session_id]
            
            print(f"[-] 断开连接: {client_id}")
            print(f"    当前连接数: {self.stats['active_connections']}")
    
    async def _process_message(
        self, 
        websocket, 
        message: str,
        session_id: str
    ):
        """处理客户端消息.
        
        Args:
            websocket: WebSocket连接
            message: 收到的消息
            session_id: 会话ID
        """
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "config":
                await self._handle_config(websocket, data, session_id)
            elif msg_type == "audio":
                await self._handle_audio(websocket, data, session_id)
            elif msg_type == "end":
                await self._handle_end(websocket, data, session_id)
            else:
                print(f"[!] 未知消息类型: {msg_type}")
                
        except json.JSONDecodeError:
            print(f"[!] 无效的JSON: {message[:100]}")
        except Exception as e:
            print(f"[!] 处理消息错误: {e}")
    
    async def _handle_config(
        self, 
        websocket, 
        data: dict,
        session_id: str
    ):
        """处理配置消息.
        
        Args:
            websocket: WebSocket连接
            data: 配置数据
            session_id: 会话ID
        """
        config_data = data.get("data", {})
        sample_rate = config_data.get("sample_rate", 16000)
        language = config_data.get("language", "zh-CN")
        
        print(f"    [配置] 采样率: {sample_rate}Hz, 语言: {language}")
        
        # 发送配置确认
        response = {
            "type": "event",
            "event_type": "config_received",
            "timestamp_ms": int(time.time() * 1000),
            "data": {
                "session_id": session_id,
                "status": "ready"
            }
        }
        await websocket.send(json.dumps(response))
    
    async def _handle_audio(
        self, 
        websocket, 
        data: dict,
        session_id: str
    ):
        """处理音频消息.
        
        Args:
            websocket: WebSocket连接
            data: 音频数据
            session_id: 会话ID
        """
        seq = data.get("seq", 0)
        audio_b64 = data.get("data", "")
        
        try:
            audio_data = base64.b64decode(audio_b64)
            self.audio_buffer[session_id].append(audio_data)
            
            self.stats['total_audio_chunks'] += 1
            duration_ms = len(audio_data) / 32  # 16kHz * 2 bytes = 32 bytes/ms
            self.stats['total_duration_ms'] += int(duration_ms)
            
            # 每10个包打印一次
            if seq % 10 == 0:
                print(f"    [音频] Seq: {seq}, Size: {len(audio_data)} bytes, "
                      f"Duration: {duration_ms:.1f}ms")
            
            # 根据模式返回结果
            await self._send_result(websocket, seq, session_id, is_final=False)
            
        except Exception as e:
            print(f"[!] 处理音频错误: {e}")
    
    async def _handle_end(
        self, 
        websocket, 
        data: dict,
        session_id: str
    ):
        """处理结束消息.
        
        Args:
            websocket: WebSocket连接
            data: 结束消息
            session_id: 会话ID
        """
        seq = data.get("seq", 0)
        print(f"    [结束] Seq: {seq}")
        
        # 发送最终结果
        await self._send_result(websocket, seq, session_id, is_final=True)
        
        # 打印统计
        audio_data = b"".join(self.audio_buffer.get(session_id, []))
        total_duration = len(audio_data) / 32000  # 秒
        print(f"    [统计] 总音频: {len(audio_data)} bytes, "
              f"时长: {total_duration:.2f}s")
    
    async def _send_result(
        self, 
        websocket, 
        seq: int,
        session_id: str,
        is_final: bool = False
    ):
        """发送识别结果.
        
        Args:
            websocket: WebSocket连接
            seq: 序列号
            session_id: 会话ID
            is_final: 是否为最终结果
        """
        # 模拟延迟
        if self.delay_ms > 0:
            await asyncio.sleep(self.delay_ms)
        
        if self.mode == "echo":
            text = f"Echo: 收到第{seq}个音频包"
        elif self.mode == "random":
            text = random.choice(self.MOCK_TEXTS)
        elif self.mode == "error":
            # 模拟错误
            if random.random() < 0.1:  # 10%概率返回错误
                error_response = {
                    "type": "error",
                    "code": 1001,
                    "message": "模拟错误: 音频格式不正确"
                }
                await websocket.send(json.dumps(error_response))
                return
            text = random.choice(self.MOCK_TEXTS)
        else:
            text = "测试文本"
        
        # 构建结果消息
        result_data = {
            "utterance_id": session_id,
            "is_final": is_final,
            "text": text,
            "confidence": random.uniform(0.8, 0.99),
            "start_time_ms": 0,
            "end_time_ms": seq * 100,
        }
        
        if is_final:
            # 最终结果添加词信息
            words = text[:len(text)//2]
            result_data["word_list"] = [
                {
                    "word": words,
                    "start_time_ms": 0,
                    "end_time_ms": seq * 50,
                    "confidence": 0.95
                }
            ]
        
        response = {
            "type": "result",
            "code": 0,
            "message": "success",
            "data": result_data
        }
        
        await websocket.send(json.dumps(response))
        
        if is_final:
            print(f"    [结果] 最终: {text}")
        elif seq % 5 == 0:
            print(f"    [结果] 中间: {text}")
    
    def _save_audio(self, session_id: str):
        """保存音频文件.
        
        Args:
            session_id: 会话ID
        """
        try:
            audio_data = b"".join(self.audio_buffer.get(session_id, []))
            if not audio_data:
                return
            
            # 创建保存目录
            save_dir = Path("saved_audio")
            save_dir.mkdir(exist_ok=True)
            
            # 保存为WAV文件
            filename = save_dir / f"{session_id}_{int(time.time())}.wav"
            
            with wave.open(str(filename), 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(audio_data)
            
            print(f"    [保存] 音频已保存: {filename}")
            
        except Exception as e:
            print(f"[!] 保存音频失败: {e}")
    
    async def start(self):
        """启动服务器."""
        print("=" * 60)
        print("ASR服务端测试程序")
        print("=" * 60)
        print(f"监听地址: ws://{self.host}:{self.port}")
        print(f"测试模式: {self.mode}")
        print(f"模拟延迟: {self.delay_ms * 1000:.0f}ms")
        print("=" * 60)
        print("按 Ctrl+C 停止服务器\n")
        
        async with websockets.serve(
            self.handle_client,
            self.host,
            self.port,
            ping_interval=30,
            ping_timeout=10
        ):
            try:
                await asyncio.Future()  # 永久运行
            except asyncio.CancelledError:
                pass
    
    def print_stats(self):
        """打印统计信息."""
        print("\n" + "=" * 60)
        print("统计信息:")
        print(f"  总连接数: {self.stats['total_connections']}")
        print(f"  活跃连接: {self.stats['active_connections']}")
        print(f"  音频包数: {self.stats['total_audio_chunks']}")
        print(f"  音频时长: {self.stats['total_duration_ms'] / 1000:.2f}s")
        print("=" * 60 + "\n")


def main():
    """主函数."""
    parser = argparse.ArgumentParser(
        description="ASR服务端测试程序",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
测试模式说明:
  echo    - 返回Echo文本，显示收到的音频包序号
  random  - 返回随机模拟文本（默认）
  delay   - 长延迟模式，测试客户端超时处理
  error   - 随机返回错误，测试客户端错误处理

示例:
  # 默认模式
  python asr_server_test.py
  
  # 指定端口和模式
  python asr_server_test.py --port 8080 --mode random
  
  # 模拟高延迟
  python asr_server_test.py --mode delay --delay 2000
        """
    )
    
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="监听地址 (默认: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="监听端口 (默认: 8765)"
    )
    parser.add_argument(
        "--mode",
        choices=["echo", "random", "delay", "error"],
        default="random",
        help="测试模式 (默认: random)"
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=500,
        help="模拟延迟（毫秒） (默认: 500)"
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="不保存接收到的音频文件"
    )
    
    args = parser.parse_args()
    
    # 创建服务器
    server = MockASRServer(
        host=args.host,
        port=args.port,
        mode=args.mode,
        delay_ms=args.delay
    )
    
    server.save_audio = not args.no_save
    
    try:
        # 启动服务器请继续说话
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\n\n[!] 服务器停止")
        server.print_stats()


if __name__ == "__main__":
    main()
