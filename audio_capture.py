"""音频采集模块 - 实时录制麦克风音频."""

import queue
import threading
import wave
from typing import Optional, Callable

import pyaudio


class AudioCapture:
    """
    音频采集器，录制16kHz单声道PCM音频.
    
    特性:
    - 16kHz采样率
    - 单声道
    - 16bit位深
    - 小端字节序
    - 支持实时回调
    """
    
    # 音频参数
    SAMPLE_RATE = 16000
    CHANNELS = 1
    SAMPLE_WIDTH = 2  # 16bit
    CHUNK_DURATION_MS = 100  # 每块100ms
    CHUNK_SIZE = int(SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS * CHUNK_DURATION_MS / 1000)
    
    def __init__(
        self,
        on_audio_chunk: Optional[Callable[[bytes], None]] = None,
        buffer_size: int = 10
    ):
        """初始化音频采集器.
        
        Args:
            on_audio_chunk: 音频块回调函数，每次采集到数据时调用
            buffer_size: 音频缓冲区大小（块数）
        """
        self.on_audio_chunk = on_audio_chunk
        self._audio = pyaudio.PyAudio()
        self._stream: Optional[pyaudio.Stream] = None
        self._is_recording = False
        self._audio_queue: queue.Queue = queue.Queue(maxsize=buffer_size)
        self._recording_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # 存储的音频数据（用于调试）
        self._recorded_data: list = []
    
    def start(self) -> bool:
        """开始录音.
        
        Returns:
            是否成功启动
        """
        with self._lock:
            if self._is_recording:
                print("已经在录音中")
                return True
            
            try:
                self._stream = self._audio.open(
                    format=pyaudio.paInt16,
                    channels=self.CHANNELS,
                    rate=self.SAMPLE_RATE,
                    input=True,
                    frames_per_buffer=self.CHUNK_SIZE,
                    stream_callback=self._audio_callback
                )
                
                self._is_recording = True
                self._recorded_data = []
                
                print(f"开始录音: {self.SAMPLE_RATE}Hz, {self.CHANNELS}ch, 16bit")
                return True
                
            except Exception as e:
                print(f"启动录音失败: {e}")
                return False
    
    def stop(self):
        """停止录音."""
        with self._lock:
            if not self._is_recording:
                return
            
            self._is_recording = False
            
            if self._stream:
                self._stream.stop_stream()
                self._stream.close()
                self._stream = None
            
            print("停止录音")
    
    def _audio_callback(
        self, 
        in_data: bytes, 
        frame_count: int, 
        time_info: dict, 
        status: int
    ) -> tuple:
        """音频回调函数.
        
        Args:
            in_data: 音频数据
            frame_count: 帧数
            time_info: 时间信息
            status: 状态标志
            
        Returns:
            (数据, 状态)
        """
        if self._is_recording:
            # 存储数据（用于调试）
            self._recorded_data.append(in_data)
            
            # 放入队列
            try:
                self._audio_queue.put_nowait(in_data)
            except queue.Full:
                # 队列满，丢弃最旧的数据
                try:
                    self._audio_queue.get_nowait()
                    self._audio_queue.put_nowait(in_data)
                except queue.Empty:
                    pass
            
            # 触发回调
            if self.on_audio_chunk:
                self.on_audio_chunk(in_data)
        
        return (in_data, pyaudio.paContinue)
    
    def get_audio_chunk(self, timeout: float = 0.1) -> Optional[bytes]:
        """从队列获取音频块.
        
        Args:
            timeout: 超时时间（秒）
            
        Returns:
            音频数据或None
        """
        try:
            return self._audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def is_recording(self) -> bool:
        """检查是否在录音中."""
        with self._lock:
            return self._is_recording
    
    def get_recorded_audio(self) -> bytes:
        """获取所有录制的音频数据.
        
        Returns:
            完整的音频数据
        """
        return b"".join(self._recorded_data)
    
    def save_to_file(self, filename: str):
        """保存录音到WAV文件（用于调试）.
        
        Args:
            filename: 文件名
        """
        if not self._recorded_data:
            print("没有录音数据")
            return
        
        try:
            with wave.open(filename, 'wb') as wf:
                wf.setnchannels(self.CHANNELS)
                wf.setsampwidth(self.SAMPLE_WIDTH)
                wf.setframerate(self.SAMPLE_RATE)
                wf.writeframes(b"".join(self._recorded_data))
            print(f"音频已保存: {filename}")
        except Exception as e:
            print(f"保存音频失败: {e}")
    
    def __del__(self):
        """析构函数."""
        self.stop()
        if self._audio:
            self._audio.terminate()


# 测试代码
if __name__ == "__main__":
    import time
    import sys
    
    def on_chunk(data: bytes):
        print(f"收到音频块: {len(data)} bytes", end="\r")
    
    print("测试音频采集")
    print("- 录音5秒")
    print("- 按Ctrl+C提前结束")
    print()
    
    capture = AudioCapture(on_audio_chunk=on_chunk)
    
    if capture.start():
        try:
            # 录音5秒
            time.sleep(5)
        except KeyboardInterrupt:
            print("\n用户中断")
        finally:
            capture.stop()
            
            # 保存录音
            capture.save_to_file("test_recording.wav")
            
            # 统计信息
            audio_data = capture.get_recorded_audio()
            duration = len(audio_data) / (capture.SAMPLE_RATE * capture.SAMPLE_WIDTH)
            print(f"\n录制时长: {duration:.2f}秒")
            print(f"数据大小: {len(audio_data)} bytes")
    else:
        print("启动录音失败")
        sys.exit(1)
