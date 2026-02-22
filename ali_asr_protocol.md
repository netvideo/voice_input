# 阿里云智能语音交互 WebSocket API 协议

## 概述

本文档描述阿里云智能语音交互产品的 WebSocket 实时语音识别协议。

**官方文档**: https://help.aliyun.com/zh/isi/developer-reference/websocket

## 接入地址

| 类型 | 地址 |
|------|------|
| 外网 | `wss://nls-gateway-cn-shanghai.aliyuncs.com/ws/v1?token=<token>` |
| 内网 | `ws://nls-gateway-cn-shanghai-internal.aliyuncs.com:80/ws/v1?token=<token>` |

## 认证

通过 URL 参数传入 Token：
```
wss://nls-gateway-cn-shanghai.aliyuncs.com/ws/v1?token=<your_token>
```

获取 Token 参考: https://help.aliyun.com/zh/isi/overview-of-obtaining-an-access-token

## 协议格式

### 消息类型

1. **文本消息 (Text Frame)**: 指令和事件
2. **二进制消息 (Binary Frame)**: 音频数据

### 指令 (客户端 → 服务器)

#### 1. StartTranscription - 开始识别

```json
{
    "header": {
        "message_id": "05450bf69c53413f8d88aed1ee60****",
        "task_id": "640bc797bb684bd6960185651307****",
        "namespace": "SpeechTranscriber",
        "name": "StartTranscription",
        "appkey": "your_appkey"
    },
    "payload": {
        "format": "PCM",
        "sample_rate": 16000,
        "enable_intermediate_result": true,
        "enable_punctuation_prediction": true,
        "enable_inverse_text_normalization": true,
        "vocabulary_id": "可选热词ID"
    }
}
```

**Payload 参数说明:**

| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| format | String | 否 | 音频格式: PCM, WAV, OPUS, SPEEX, AMR, MP3, AAC |
| sample_rate | Integer | 否 | 采样率: 8000, 16000 (默认) |
| enable_intermediate_result | Boolean | 否 | 返回中间结果 |
| enable_punctuation_prediction | Boolean | 否 | 添加标点 |
| enable_inverse_text_normalization | Boolean | 否 | ITN中文数字转阿拉伯数字 |
| vocabulary_id | String | 否 | 热词ID |
| customization_id | String | 否 | 自学习模型ID |

#### 2. StopTranscription - 停止识别

```json
{
    "header": {
        "message_id": "05450bf69c53413f8d88aed1ee60****",
        "task_id": "640bc797bb684bd6960185651307****",
        "namespace": "SpeechTranscriber",
        "name": "StopTranscription",
        "appkey": "your_appkey"
    }
}
```

### 事件 (服务器 → 客户端)

#### 1. TranscriptionStarted - 开始成功

```json
{
    "header": {
        "message_id": "...",
        "task_id": "...",
        "namespace": "SpeechTranscriber",
        "name": "TranscriptionStarted",
        "status": 20000000,
        "status_message": "GATEWAY|SUCCESS|Success."
    },
    "payload": {
        "session_id": "1231231dfdf****"
    }
}
```

#### 2. SentenceBegin - 句子开始

```json
{
    "header": {
        "name": "SentenceBegin",
        "status": 20000000
    },
    "payload": {
        "index": 1,
        "time": 320
    }
}
```

#### 3. TranscriptionResultChanged - 中间结果

```json
{
    "header": {
        "name": "TranscriptionResultChanged",
        "status": 20000000
    },
    "payload": {
        "index": 1,
        "time": 1800,
        "result": "今年双十一"
    }
}
```

#### 4. SentenceEnd - 句子结束 (最终结果)

```json
{
    "header": {
        "name": "SentenceEnd",
        "status": 20000000
    },
    "payload": {
        "index": 1,
        "time": 3260,
        "begin_time": 1800,
        "result": "今年双十一我要买电视",
        "confidence": 0.95
    }
}
```

#### 5. TranscriptionCompleted - 识别完成

```json
{
    "header": {
        "name": "TranscriptionCompleted",
        "status": 20000000
    }
}
```

## 状态码

| 状态码 | 说明 |
|--------|------|
| 20000000 | 成功 |
| 40000001 | 参数错误 |
| 40000002 | 无效消息 |
| 40000003 | Token无效 |
| 40000004 | Appkey无效 |
| 40000005 | 服务端错误 |
| 40000006 | 超过并发 |
| 40000007 | 已达到上限 |

## 使用示例

```python
from ali_asr_client import AliASRClient, get_token

# 方式1: 直接使用Token
client = AliASRClient(
    token="your_token",
    appkey="your_appkey",
    enable_intermediate_result=True,
    enable_punctuation=True,
    enable_itn=True,
    on_result=lambda text, is_final: print(f"[{'最终' if is_final else '中间'}] {text}")
)

client.start()

# 发送音频 (PCM 16kHz 16bit)
with open("audio.pcm", "rb") as f:
    while chunk := f.read(3200):  # 100ms
        client.send_audio(chunk)
        time.sleep(0.1)

client.stop()

# 方式2: 获取Token
token = get_token("your_access_key_id", "your_access_key_secret")
```

## 音频格式要求

| 参数 | 要求 |
|------|------|
| 声道 | 单声道 (mono) |
| 位深 | 16 bit |
| 采样率 | 8000 Hz 或 16000 Hz |
| 编码 | PCM, WAV, OPUS, SPEEX, AMR, MP3, AAC |

## 注意事项

1. `message_id` 每次发送需要不同
2. `task_id` 在整个会话中保持不变
3. 音频数据使用 Binary Frame 发送
4. 发送音频后需要等待 `TranscriptionStarted` 事件后再发送音频
5. 建议每次发送 3200 字节 (100ms @ 16kHz)
