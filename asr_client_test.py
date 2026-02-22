"""ASR客户端测试工具.

功能:
- 测试与ASR服务器的连接
- 支持麦克风实时测试
- 支持音频文件测试
- 显示详细的通信日志

使用方法:
    # 测试服务器连接
    python asr_client_test.py --url ws://localhost:8765
    
    # 使用麦克风测试
    python asr_client_test.py --url ws://localhost:8765 --mic
    
    # 使用音频文件测试
    python asr_client_test.py --url ws://localhost:8765 --file test.wav
"""

import argparse
import asyncio
import base64
import json
import sys
import time
from pathlib import Path
from typing import Optional

import pyaudio
import websockets


class ASRClientTest:
    """ASR客户端测试工具."""
    
    # 音频参数
    SAMPLE_RATE = 16000
    CHANNELS = 1
    SAMPLE_WIDTH = 2
    CHUNK_DURATION_MS = 100
    CHUNK_SIZE = int(SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS * CHUNK_DURATION_MS / 1000)
    
    def __init__(self, url: str, verbose: bool = True):
        """初始化测试客户端.
        
        Args:
            url: WebSocket服务器地址
            verbose: 是否显示详细日志
        """
        self.url = url
        self.verbose = verbose
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        
        # 统计
        self.stats = {
            'chunks_sent': 0,
            'results_received': 0,
            'start_time': 0,
        }
    
    def log(self, message: str, level: str = "INFO"):
        """打印日志.
        
        Args:
            message: 消息
            level: 日志级别
        """
        if self.verbose or level in ["ERROR", "WARN"]:
            prefix = {"INFO": "[i]", "OK": "[✓]", "WARN": "[!]", "ERROR": "[✗]"}.get(level, "[i]")
            print(f"{prefix} {message}")
    
    async def test_connection(self) -> bool:
        """测试服务器连接.
        
        Returns:
            是否连接成功
        """
        self.log(f"连接到服务器: {self.url}")
        
        try:
            self.websocket = await websockets.connect(self.url)
            self.log("连接成功", "OK")
            
            # 发送配置
            config = {
                "type": "config",
                "data": {
                    "sample_rate": self.SAMPLE_RATE,
                    "channels": self.CHANNELS,
                    "sample_width": self.SAMPLE_WIDTH,
                    "language": "zh-CN",
                    "enable_punctuation": True,
                    "enable_itn": True
                }
            }
            
            await self.websocket.send(json.dumps(config))
            self.log("配置已发送")
            
            # 等待响应
            response = await asyncio.wait_for(
                self.websocket.recv(),
                timeout=5.0
            )
            
            data = json.loads(response)
            if data.get("type") == "event":
                self.log(f"服务器就绪: {data.get('data', {}).get('session_id', 'unknown')}", "OK")
                return True
            else:
                self.log(f"意外的响应: {response}", "WARN")
                return True
                
        except Exception as e:
            self.log(f"连接失败: {e}", "ERROR")
            return False
    
    async def test_with_mic(self, duration: float = 5.0):
        """使用麦克风测试.
        
        Args:
            duration: 录音时长（秒）
        """
        if not await self.test_connection():
            return
        
        self.log(f"开始麦克风测试，时长: {duration}s")
        self.log("请对着麦克风说话...")
        
        # 初始化音频
        audio = pyaudio.PyAudio()
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=self.CHANNELS,
            rate=self.SAMPLE_RATE,
            input=True,
            frames_per_buffer=self.CHUNK_SIZE
        )
        
        self.stats['start_time'] = time.time()
        
        try:
            # 启动接收任务
            receive_task = asyncio.create_task(self._receive_loop())
            
            # 发送音频
            start_time = time.time()
            seq = 0
            
            while time.time() - start_time < duration:
                # 读取音频
                data = stream.read(self.CHUNK_SIZE, exception_on_overflow=False)
                
                # 发送
                message = {
                    "type": "audio",
                    "seq": seq,
                    "is_final": False,
                    "data": base64.b64encode(data).decode('utf-8')
                }
                
                await self.websocket.send(json.dumps(message))
                self.stats['chunks_sent'] += 1
                seq += 1
                
                # 每10个包打印一次
                if seq % 10 == 0:
                    elapsed = time.time() - start_time
                    print(f"\r    已发送: {seq} 包, 时长: {elapsed:.1f}s", end="")
                
                await asyncio.sleep(0.001)  # 短暂休眠避免阻塞
            
            print()  # 换行
            
            # 发送结束
            await self.websocket.send(json.dumps({"type": "end", "seq": seq}))
            self.log("音频发送完成")
            
            # 等待最终结果
            await asyncio.sleep(2.0)
            
            # 取消接收任务
            receive_task.cancel()
            
        except Exception as e:
            self.log(f"测试出错: {e}", "ERROR")
        finally:
            stream.stop_stream()
            stream.close()
            audio.terminate()
            
            await self.close()
            self._print_stats()
    
    async def test_with_file(self, file_path: str):
        """使用音频文件测试.
        
        Args:
            file_path: 音频文件路径
        """
        if not await self.test_connection():
            return
        
        file_path = Path(file_path)
        if not file_path.exists():
            self.log(f"文件不存在: {file_path}", "ERROR")
            return
        
        self.log(f"使用文件测试: {file_path}")
        
        # 读取文件
        try:
            import wave
            with wave.open(str(file_path), 'rb') as wf:
                n_channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                sample_rate = wf.getframerate()
                n_frames = wf.getnframes()
                
                self.log(f"音频信息: {n_channels}ch, {sample_width}bytes, {sample_rate}Hz, {n_frames}frames")
                
                # 读取数据
                audio_data = wf.readframes(n_frames)
                
        except Exception as e:
            self.log(f"读取文件失败: {e}", "ERROR")
            # 尝试作为原始PCM读取
            audio_data = file_path.read_bytes()
            self.log(f"作为原始PCM读取: {len(audio_data)} bytes")
        
        self.stats['start_time'] = time.time()
        
        try:
            # 启动接收任务
            receive_task = asyncio.create_task(self._receive_loop())
            
            # 分块发送
            chunk_size = self.CHUNK_SIZE
            seq = 0
            total_chunks = len(audio_data) // chunk_size
            
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i:i+chunk_size]
                
                message = {
                    "type": "audio",
                    "seq": seq,
                    "is_final": False,
                    "data": base64.b64encode(chunk).decode('utf-8')
                }
                
                await self.websocket.send(json.dumps(message))
                self.stats['chunks_sent'] += 1
                seq += 1
                
                # 每10个包打印一次
                if seq % 10 == 0:
                    progress = seq / total_chunks * 100
                    print(f"\r    已发送: {seq}/{total_chunks} 包 ({progress:.1f}%)", end="")
                
                # 模拟实时发送
                await asyncio.sleep(0.1)
            
            print()  # 换行
            
            # 发送结束
            await self.websocket.send(json.dumps({"type": "end", "seq": seq}))
            self.log("音频发送完成")
            
            # 等待最终结果
            await asyncio.sleep(2.0)
            
            # 取消接收任务
            receive_task.cancel()
            
        except Exception as e:
            self.log(f"测试出错: {e}", "ERROR")
        finally:
            await self.close()
            self._print_stats()
    
    async def _receive_loop(self):
        """接收消息循环."""
        try:
            while True:
                message = await self.websocket.recv()
                data = json.loads(message)
                
                msg_type = data.get("type")
                
                if msg_type == "result":
                    result_data = data.get("data", {})
                    text = result_data.get("text", "")
                    is_final = result_data.get("is_final", False)
                    confidence = result_data.get("confidence", 0)
                    
                    prefix = "[最终结果]" if is_final else "[中间结果]"
                    self.log(f"{prefix} {text} (置信度: {confidence:.2f})")
                    self.stats['results_received'] += 1
                    
                elif msg_type == "event":
                    event_type = data.get("event_type")
                    self.log(f"[事件] {event_type}")
                    
                elif msg_type == "error":
                    code = data.get("code")
                    message = data.get("message")
                    self.log(f"[错误] [{code}] {message}", "ERROR")
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.log(f"接收错误: {e}", "ERROR")
    
    async def close(self):
        """关闭连接."""
        if self.websocket:
            await self.websocket.close()
            self.log("连接已关闭")
    
    def _print_stats(self):
        """打印统计信息."""
        elapsed = time.time() - self.stats['start_time']
        print("\n" + "=" * 50)
        print("测试统计:")
        print(f"  运行时间: {elapsed:.2f}s")
        print(f"  发送包数: {self.stats['chunks_sent']}")
        print(f"  接收结果: {self.stats['results_received']}")
        if elapsed > 0:
            print(f"  发送速率: {self.stats['chunks_sent'] / elapsed:.1f} 包/秒")
        print("=" * 50 + "\n")


def main():
    """主函数."""
    parser = argparse.ArgumentParser(
        description="ASR客户端测试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 测试服务器连接
  python asr_client_test.py
  
  # 指定服务器地址
  python asr_client_test.py --url ws://localhost:8765
  
  # 使用麦克风测试
  python asr_client_test.py --url ws://localhost:8765 --mic --duration 10
  
  # 使用音频文件测试
  python asr_client_test.py --url ws://localhost:8765 --file test.wav
        """
    )
    
    parser.add_argument(
        "--url",
        default="ws://localhost:8765",
        help="服务器地址 (默认: ws://localhost:8765)"
    )
    parser.add_argument(
        "--mic",
        action="store_true",
        help="使用麦克风测试"
    )
    parser.add_argument(
        "--file",
        help="使用音频文件测试"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=5.0,
        help="麦克风录音时长（秒） (默认: 5)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="安静模式，减少日志输出"
    )
    
    args = parser.parse_args()
    
    # 创建客户端
    client = ASRClientTest(
        url=args.url,
        verbose=not args.quiet
    )
    
    try:
        # 运行测试
        if args.mic:
            asyncio.run(client.test_with_mic(duration=args.duration))
        elif args.file:
            asyncio.run(client.test_with_file(args.file))
        else:
            # 仅测试连接
            asyncio.run(client.test_connection_and_close())
    except KeyboardInterrupt:
        print("\n[!] 测试中断")


if __name__ == "__main__":
    # 添加兼容方法
    async def test_connection_and_close(self):
        """仅测试连接并关闭."""
        if await self.test_connection():
            self.log("连接测试成功", "OK")
            await self.close()
        else:
            sys.exit(1)
    
    ASRClientTest.test_connection_and_close = test_connection_and_close
    
    main()
