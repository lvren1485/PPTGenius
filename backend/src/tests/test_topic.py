"""Single-topic API test: create outline → confirm → generate content. Usage: python test_topic.py <topic_name>"""
import asyncio
import io
import json
import sys
import time

sys.path.insert(0, "src")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import httpx
from pptgenius.infrastructure.config.settings import get_settings
from pptgenius.infrastructure.auth import create_token
from pptgenius.infrastructure.db.database import Database
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

BASE = "http://localhost:8000"
TOPICS = {
    "ai_education": {
        "turn1": "帮我创建一个关于AI教育的PPT大纲，标题为'人工智能教育的未来'，3个章节，共12页。涵盖AI教学工具、个性化学习、教师角色转变。",
        "turn2": "大纲看起来不错，请为所有章节填充详细内容。",
    },
    "carbon_neutral": {
        "turn1": "帮我创建一个关于碳中和的PPT大纲，标题为'碳中和路径与实践'，3个章节，共12页。涵盖碳排放现状、减排技术、政策与企业实践。",
        "turn2": "好的，请为所有章节填充详细内容。",
    },
    "remote_work": {
        "turn1": "帮我创建一个关于远程办公的PPT大纲，标题为'远程办公新范式'，3个章节，共12页。涵盖工具平台、团队协作、未来趋势。",
        "turn2": "确认大纲，请为所有章节填充详细内容。",
    },
}


async def setup(topic: str) -> dict:
    settings = get_settings()
    engine = create_async_engine(settings.db.url, echo=False)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        db = Database(session)
        user = await db.get_user_by_name("apitest")
        if not user:
            user = await db.create_user(name="apitest", password="apitest123")
        conv = await db.create_conversation(user.id, title=f"Test-{topic}")
        conv_id = conv.id
        user_id = user.id
    await engine.dispose()
    token = create_token(user_id)
    return {"token": token, "user_id": user_id, "conversation_id": conv_id}


async def chat(topic: str, cfg: dict, turn: int, msg: str):
    label = f"[{topic}] Turn {turn}"
    print(f"\n{'#'*60}")
    print(f"# {label}")
    print(f"# {msg[:100]}")
    print(f"{'#'*60}")

    t0 = time.time()
    headers = {"Authorization": f"Bearer {cfg['token']}"}
    async with httpx.AsyncClient(timeout=900) as client:
        async with client.stream(
            "POST", f"{BASE}/api/chat/send",
            json={"user_id": cfg["user_id"], "conversation_id": cfg["conversation_id"], "message": msg},
            headers=headers,
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                print(f"  [{topic}] HTTP {resp.status_code}: {body.decode()[:300]}")
                return

            last_reply = ""
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    d = json.loads(line[5:].strip())
                    t = d.get("type", "")
                    if t == "master_reply":
                        last_reply = d.get("reply", "")
                    elif t == "done":
                        print(f"  [{topic}] done cost=${d.get('estimated_cost',0):.4f} elapsed={d.get('elapsed_seconds',0)}s")
                    elif t == "error":
                        print(f"  [{topic}] ERROR: {d.get('message','')}")
                        return
            elapsed = round(time.time() - t0, 1)
            print(f"  [{topic}] [{elapsed}s] reply: {last_reply[:200].replace(chr(10),' ')}...")


async def main():
    topic = sys.argv[1] if len(sys.argv) > 1 else "ai_education"
    msgs = TOPICS.get(topic)
    if not msgs:
        print(f"Unknown topic: {topic}")
        return

    print(f"[{topic}] Setting up conversation...")
    cfg = await setup(topic)
    print(f"[{topic}] conv={cfg['conversation_id']} user={cfg['user_id']}")

    await chat(topic, cfg, 1, msgs["turn1"])
    await chat(topic, cfg, 2, msgs["turn2"])
    print(f"\n[{topic}] DONE")


if __name__ == "__main__":
    asyncio.run(main())
