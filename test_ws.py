import asyncio
import json
import websockets

async def test_ws():
    uri = 'ws://localhost:8000/ws'
    try:
        async with websockets.connect(uri) as ws:
            print("Connected to WebSocket")

            # Send ping first
            await ws.send(json.dumps({'type': 'ping'}))
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            print(f"Ping response: {msg}")

            # Send a command
            await ws.send(json.dumps({'type': 'command', 'command': 'Check BTC price'}))
            print("Sent command: Check BTC price")

            # Listen for messages
            for _ in range(15):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(msg)
                    print(f"Type: {data.get('type')}")
                    if data.get('type') != 'pong':
                        print(f"Data: {json.dumps(data.get('data', {}), indent=2)[:300]}")
                    print('---')
                except asyncio.TimeoutError:
                    print('Timeout - no more messages')
                    break
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(test_ws())
