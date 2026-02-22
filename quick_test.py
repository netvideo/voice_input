"""快速测试脚本."""
import asyncio
import json
import websockets

async def test_server():
    """测试服务器."""
    uri = "ws://localhost:8765/asr/v1/stream"
    
    print(f"连接服务器: {uri}")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("连接成功!")
            
            # 发送配置
            config = {
                "type": "config",
                "data": {
                    "sample_rate": 16000,
                    "channels": 1,
                    "language": "zh-CN"
                }
            }
            
            await websocket.send(json.dumps(config))
            print("配置已发送")
            
            # 等待响应
            response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            data = json.loads(response)
            print(f"服务器响应: {data}")
            
            if data.get("type") == "event":
                print("✓ 服务器已就绪!")
                return True
            else:
                print("✗ 意外的响应")
                return False
                
    except Exception as e:
        print(f"✗ 连接失败: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_server())
    exit(0 if result else 1)
