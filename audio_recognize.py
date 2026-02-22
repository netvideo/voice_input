#!/usr/bin/env python
"""音频文件识别工具 - 从音频文件识别语音并保存结果.

用法:
    python audio_recognize.py <音频文件> [--url ws://127.0.0.1:8765] [--lang zh-CN] [--output result.txt]
"""

import argparse
import asyncio
import base64
import json
import sys
from pathlib import Path

import numpy as np
import websockets


def load_audio(file_path: str, target_rate: int = 16000) -> tuple[bytes, int]:
    """加载音频文件."""
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    # 尝试加载WAV
    if path.suffix.lower() == ".wav":
        import wave
        with wave.open(file_path, "rb") as wf:
            frames = wf.readframes(wf.getnframes())
            orig_rate = wf.getframerate()
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
        
        # 转换
        if sampwidth == 2:
            audio = np.frombuffer(frames, dtype=np.int16)
        else:
            audio = np.frombuffer(frames, dtype=np.uint8).astype(np.int16) - 128
        
        # 转单声道
        if channels > 1:
            audio = audio.reshape(-1, channels).mean(axis=1).astype(np.int16)
        
        # 重采样
        if orig_rate != target_rate:
            indices = np.linspace(0, len(audio) - 1, int(len(audio) * target_rate / orig_rate))
            audio = np.interp(indices, np.arange(len(audio)), audio).astype(np.int16)
        
        return audio.tobytes(), target_rate
    
    raise ValueError(f"仅支持WAV文件。如需支持其他格式，请安装 pydub: pip install pydub")


async def recognize_audio(file_path: str, ws_url: str, language: str) -> str:
    """识别音频文件."""
    print(f"加载: {file_path}")
    audio_data, sample_rate = load_audio(file_path)
    duration = len(audio_data) / sample_rate
    print(f"采样率: {sample_rate}Hz, 时长: {duration:.2f}s")
    print(f"服务器: {ws_url}")
    
    async with websockets.connect(ws_url) as ws:
        # 发送配置
        await ws.send(json.dumps({
            "type": "config",
            "data": {"language": language}
        }))
        
        # 等待就绪
        resp = await asyncio.wait_for(ws.recv(), timeout=10.0)
        print("服务器就绪")
        
        # 分块发送
        chunk_size = int(sample_rate * 0.1 * 2)
        seq = 0
        
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i + chunk_size]
            is_final = (i + chunk_size) >= len(audio_data)
            
            await ws.send(json.dumps({
                "type": "audio",
                "seq": seq,
                "is_final": is_final,
                "data": base64.b64encode(chunk).decode()
            }))
            seq += 1
            
            # 接收结果
            try:
                resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(resp)
                
                if data.get("type") == "result":
                    text = data.get("data", {}).get("text", "")
                    is_final = data.get("data", {}).get("is_final", False)
                    
                    if is_final:
                        return text
                    print(f"  -> {text}")
            except asyncio.TimeoutError:
                pass
        
        # 发送结束
        await ws.send(json.dumps({"type": "end", "seq": seq}))
    
    return ""


async def main():
    parser = argparse.ArgumentParser(description="音频文件识别")
    parser.add_argument("file", help="音频文件(WAV)")
    parser.add_argument("--url", default="ws://127.0.0.1:8765", help="ASR服务器")
    parser.add_argument("--lang", default="zh-CN", help="语言")
    parser.add_argument("--output", "-o", help="输出文件")
    
    args = parser.parse_args()
    
    try:
        text = await recognize_audio(args.file, args.url, args.lang)
        
        print("\n" + "=" * 50)
        print("识别结果:")
        print(text)
        print("=" * 50)
        
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"\n已保存到: {args.output}")
        
    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
