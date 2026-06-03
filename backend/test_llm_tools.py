import asyncio
import json
from services.llm_factory import create_llm
from services.tools.definitions import tools_list
from browser_use.llm.messages import UserMessage

async def test():
    llm = create_llm()
    tools_json = json.dumps(tools_list, ensure_ascii=False)
    prompt = (
        f'You are an AI assistant with access to tools. '
        f'Based on the user message, select the appropriate tools to call. '
        f'Respond ONLY with a JSON array of objects, each with name and arguments.\n\n'
        f'User message: Check BTC price\n\n'
        f'Available tools: {tools_json}\n\n'
        f'If no tools are needed, respond with an empty array [].'
    )
    result = await llm.ainvoke([UserMessage(content=prompt)])
    raw = result.completion if hasattr(result, "completion") else str(result)
    print('Raw result (first 500 chars):')
    print(raw[:500])
    print('---')
    try:
        selected = json.loads(raw)
        print('Parsed JSON:', json.dumps(selected, indent=2)[:500])
    except json.JSONDecodeError as e:
        print('JSON parse error:', e)

asyncio.run(test())
