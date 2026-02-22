"""音频文件导入模块 - 从音频文件识别语音."""

import asyncio
import base64
import json
import os
import struct
import wave
from pathlib import Path
from typing import Optional, Tuple

import numpy as np


def load_audio_file(file_path: str, target_sample_rate: int = 16000) -> Tuple[bytes, int]:
    """加载音频文件并转换为16kHz 16bit PCM格式.
    
    支持格式: WAV (PCM), MP3, FLAC, OGG, M4A 等 (通过pydub/ffmpeg)
    
    Args:
        file_path: 音频文件路径
        target_sample_rate: 目标采样率 (默认16000)
        
    Returns:
        (PCM音频数据, 实际采样率)
    """
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"音频文件不存在: {file_path}")
    
    suffix = path.suffix.lower()
    
    # WAV文件 - 直接读取
    if suffix == ".wav":
        return _load_wav(file_path, target_sample_rate)
    
    # 其他格式 - 尝试使用pydub
    try:
        return _load_via_pydub(file_path, target_sample_rate)
    except ImportError:
        pass
    
    # 尝试使用soundfile
    try:
        return _load_via_soundfile(file_path, target_sample_rate)
    except ImportError:
        pass
    
    raise ValueError(f"无法加载音频文件: {file_path}。请安装 pydub 或 soundfile 库。")


def _load_wav(file_path: str, target_sample_rate: int) -> Tuple[bytes, int]:
    """加载WAV文件并转换."""
    with wave.open(file_path, "rb") as wf:
        # 获取原始参数
        sample_width = wf.getsampwidth()
        channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        
        # 读取音频数据
        frames = wf.readframes(wf.getnframes())
    
    # 转换为numpy数组
    if sample_width == 2:
        audio = np.frombuffer(frames, dtype=np.int16)
    elif sample_width == 4:
        audio = np.frombuffer(frames, dtype=np.int32).astype(np.int16)
    else:
        audio = np.frombuffer(frames, dtype=np.uint8).astype(np.int16) - 128
    
    # 转换为立体声
    if channels == 1:
        pass
    elif channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1).astype(np.int16)
    
    # 重采样
    if sample_rate != target_sample_rate:
        audio = _resample(audio, sample_rate, target_sample_rate)
    
    # 转换为字节
    pcm_data = audio.tobytes()
    
    return pcm_data, target_sample_rate


def _load_via_pydub(file_path: str, target_sample_rate: int) -> Tuple[bytes, int]:
    """通过pydub加载音频 (支持MP3等格式)."""
    from pydub import AudioSegment
    
    audio = AudioSegment.from_file(file_path)
    
    # 转换为单声道
    audio = audio.set_channels(1)
    
    # 重采样
    audio = audio.set_frame_rate(target_sample_rate)
    
    # 转换为16bit PCM
    audio = audio.set_sample_width(2)
    
    # 转换为numpy
    samples = np.array(audio.get_array_of_samples(), dtype=np.int16)
    
    return samples.tobytes(), target_sample_rate


def _load_via_soundfile(file_path: str, target_sample_rate: int) -> Tuple[bytes, int]:
    """通过soundfile加载音频."""
    import soundfile as sf
    
    audio, sample_rate = sf.read(file_path, dtype=np.float32)
    
    # 转换为单声道
    if len(audio.shape) > 1:
        audio = audio.mean(axis=1)
    
    # 归一化到16bit
    audio = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
    
    # 重采样
    if sample_rate != target_sample_rate:
        audio = _resample(audio, sample_rate, target_sample_rate)
    
    return audio.tobytes(), target_sample_rate


def _resample(audio: np.ndarray, orig_rate: int, target_rate: int) -> np.ndarray:
    """重采样音频."""
    try:
        from scipy import signal
        
        # 计算采样比
        ratio = target_rate / orig_rate
        new_length = int(len(audio) * ratio)
        
        # 重采样
        resampled = signal.resample(audio, new_length)
        return resampled.astype(np.int16)
    except ImportError:
        # 简单线性插值
        indices = np.linspace(0, len(audio) - 1, int(len(audio) * target_rate / orig_rate))
        return np.interp(indices, np.arange(len(audio)), audio).astype(np.int16)


class AudioFileRecognizer:
    """音频文件识别器 - 从音频文件识别语音."""
    
    def __init__(self, ws_url: str = "ws://127.0.0.1:8765"):
        """初始化识别器.
        
        Args:
            ws_url: ASR服务器WebSocket地址
        """
        self.ws_url = ws_url
        self._result = None
        self._error = None
        self._connected = False
    
    async def recognize(self, file_path: str, language: str = "zh-CN") -> dict:
        """识别音频文件.
        
        Args:
            file_path: 音频文件路径
            language: 语言代码
            
        Returns:
            识别结果字典
        """
        # 加载音频
        print(f"加载音频文件: {file_path}")
        audio_data, sample_rate = load_audio_file(file_path)
        print(f"音频采样率: {sample_rate}Hz, 时长: {len(audio_data) / sample_rate:.2f}s")
        
        # 连接到服务器
        print(f"连接到ASR服务器: {self.ws_url}")
        async with websockets.connect(self.ws_url) as websocket:
            # 发送配置
            await websocket.send(json.dumps({
                "type": "config",
                "data": {
                    "language": language,
                    "enable_punctuation": True,
                    "enable_itn": True
                }
            }))
            
            # 等待就绪
            response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            data = json.loads(response)
            if data.get("type") == "event" and data.get("event_type") == "config_received":
                print("服务器已就绪")
            else:
                print(f"服务器响应: {response}")
            
            # 分块发送音频
            chunk_size = int(sample_rate * 0.1 * 2)  # 100ms
            seq = 0
            
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i:i + chunk_size]
                is_final = (i + chunk_size) >= len(audio_data)
                
                await websocket.send(json.dumps({
                    "type": "audio",
                    "seq": seq,
                    "is_final": is_final,
                    "data": base64.b64encode(chunk).decode('utf-8')
                }))
                
                seq += 1
                
                # 等待识别结果
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    result = json.loads(response)
                    
                    if result.get("type") == "result":
                        text = result.get("data", {}).get("text", "")
                        is_final = result.get("data", {}).get("is_final", False)
                        
                        if is_final:
                            print(f"\n识别结果: {text}")
                            return {
                                "text": text,
                                "is_final": True,
                                "code": 0,
                                "message": "success"
                            }
                        else:
                            print(f"中间结果: {text}")
                    
                    elif result.get("type") == "error":
                        return result
                        
                except asyncio.TimeoutError:
                    print(f"等待响应超时 (chunk {seq})")
            
            # 发送结束
            await websocket.send(json.dumps({
                "type": "end",
                "seq": seq
            }))
        
        return {"text": "", "code": -1, "message": "识别失败"}
    
    def recognize_sync(self, file_path: str, language: str = "zh-CN") -> dict:
        """同步识别音频文件."""
        return asyncio.run(self.recognize(file_path, language))


# CLI测试
if __name__ == "__main__":
    import argparse
    import websockets
    
    parser = argparse.ArgumentParser(description="从音频文件识别语音")
    parser.add_argument("file", help="音频文件路径")
    parser.add_argument("--url", default="ws://127.0.0.1:8765", help="ASR服务器地址")
    parser.add_argument("--language", default="zh-CN", help="语言代码")
    
    args = parser.parse_args()
    
    recognizer = AudioFileRecognizer(args.url)
    result = recognizer.recognize_sync(args.file, args.language)
    
    print("\n" + "=" * 50)
    print("识别结果:")
    print(result.get("text", ""))
    print("=" * 50)
