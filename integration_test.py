"""集成测试 - 同时运行服务端和客户端."""
import asyncio
import json
import sys
from pathlib import Path

# 添加voice_input到路径
sys.path.insert(0, str(Path(__file__).parent))

from asr_server_test import MockASRServer


async def run_test():
    """运行集成测试."""
    # 创建服务端
    server = MockASRServer(
        host="127.0.0.1",
        port=8766,  # 使用不同端口避免冲突
        mode="random",
        delay_ms=100
    )
    server.save_audio = False
    
    # 启动服务端
    print("=" * 60)
    print("集成测试 - 服务端 + 客户端")
    print("=" * 60)
    
    server_task = asyncio.create_task(start_server(server))
    await asyncio.sleep(1)  # 等待服务端启动
    
    # 测试客户端连接
    result = await test_client()
    
    # 停止服务端
    server_task.cancel()
    try:
        await server_task
    except asyncio.CancelledError:
        pass
    
    return result


async def start_server(server):
    """启动服务端."""
    import websockets
    async with websockets.serve(
        server.handle_client,
        server.host,
        server.port
    ):
        print(f"服务端已启动: ws://{server.host}:{server.port}")
        await asyncio.Future()  # 永久运行


async def test_client():
    """测试客户端."""
    import websockets
    
    uri = "ws://127.0.0.1:8766/asr/v1/stream"
    print(f"\n测试客户端连接到: {uri}")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✓ 连接成功")
            
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
            print("✓ 配置已发送")
            
            # 等待响应
            response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            data = json.loads(response)
            
            print(f"✓ 收到响应: {data.get('type')}")
            
            if data.get("type") == "event":
                print("✓✓✓ 测试通过! 服务端和客户端通信正常")
                return True
            else:
                print(f"✗ 意外的响应类型: {data}")
                return False
                
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    result = asyncio.run(run_test())
    print("\n" + "=" * 60)
    if result:
        print("测试结果: 通过")
    else:
        print("测试结果: 失败")
    print("=" * 60)
    exit(0 if result else 1)
