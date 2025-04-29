import contextlib
import json
import re
import gzip
import base64
import asyncio
from fastapi import APIRouter, HTTPException,Body
from openai import OpenAI
from pydantic import BaseModel
from typing import List , Optional

from starlette.responses import StreamingResponse

from backend.app.game.schema.game_chat_history_schemas import ChatRequest
from backend.app.game.service.game_service import load_history, save_history, get_game, get_all_games, saving_game, \
    delete_game, update_game_name
from backend.app.game.service.getuserinfo import get_user_llm_info

router = APIRouter()

max_history_length = 50

# 定义 Pydantic 模型
class Game(BaseModel):
    uuid:str
    name: Optional[str] = None
    url: Optional[str] = None
    rules: Optional[str] = None
    code: str

class GameDeleteRequest(BaseModel):
    uuid: str



class GameResponse(BaseModel):
    uuid:str
    name: Optional[str] = None
    url: Optional[str] = None
    rules: Optional[str] = None
    code: str
    class Config:
        orm_mode = True  # 启用 ORM 模式
        from_attributes = True

@router.get('/game/get_all', response_model=List[GameResponse])
async def get_all_game():
    """
    获取所有游戏信息
    """
    try:
        games = await get_all_games()
        # 转换为 Pydantic 模型
        response = [GameResponse.from_orm(game) for game in games]
        return response
    except Exception as e:
        print("Error occurred while processing games:", str(e))  # 打印具体错误信息
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get('/game/get/{id}', response_model=GameResponse)
async def get_game_by_id(id: int):
    """
    获取指定 ID 的游戏信息
    """
    game = await get_game(id)  # 调用数据库方法获取游戏
    if not game:
        raise HTTPException(status_code=404, detail=f"Game with ID {id} not found")
    return game


@router.post('/game/save', response_model=GameResponse)
async def game_save(game: Game):
    """
    创建游戏
    """
    try:
        # 将 Pydantic 模型转换为字典并保存到数据库
        db_game = await saving_game(game.dict())
        return db_game
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving game: {str(e)}")

@router.delete('/game/delete/{uuid}')
async def game_delete(uuid: str):
    """
    删除指定游戏
    """
    success = await delete_game(uuid)  # 调用数据库方法删除游戏
    if not success:
        raise HTTPException(status_code=404, detail=f"Game with UUID {uuid} not found")
    return {"message": f"Game with ID {id} deleted"}


class UpdateGameNameRequest(BaseModel):
    new_name: str


@router.put('/game/update/{uuid}')
async def game_name_update(uuid:str,request: UpdateGameNameRequest):
    """
    修改游戏名字的 API
    :param uuid: 游戏的 UUID
    :param new_name: 新的名字
    :return: 修改结果
    """
    new_name = request.new_name  # 从请求体中提取 new_name
    if not new_name.strip():
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    success = await update_game_name(uuid, new_name)
    if not success:
        raise HTTPException(status_code=404, detail=f"Game with UUID {uuid} not found")
    return {"message": f"Game with UUID {uuid} successfully updated to name '{new_name}'"}

good_api_key = "sk-uY3KxnnEiug7Yhzi93059e944eA2468788Bb14C5108560E9"

@router.post('/game/ask')
async def api_ask_stream(request: ChatRequest):
    question = request.question
    user_token = request.user_token
    user = await get_user_llm_info(user_token=user_token)
    user_uuid = user.get('user_uuid')
    client = OpenAI(
        # api_key=user.get('api_key'),
        api_key=good_api_key,
        base_url=user.get('api_url')
    )

    history = await load_history(user_uuid=user_uuid)
    history.append(f"User: {question}\n")

    async def event_stream():
        # 心跳任务
        async def heartbeat_sender(queue):
            try:
                while True:
                    await queue.put(json.dumps({"type": "heartbeat"}) + "\n")
                    await asyncio.sleep(50)
            except asyncio.CancelledError:
                pass

        # 主任务（请求大模型）
        async def main_logic(queue):
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=user.get('model_name'),
                messages=[{"role": "system", "content": history[0]}] + [
                    {"role": "user", "content": line} for line in history[1:]
                ]
            )
            assistant_reply = response.choices[0].message.content
            history.append(f"Assistant: {assistant_reply}\n")
            if len(history) > max_history_length * 2 + 1:
                history[:] = history[-(max_history_length * 2 + 1):]
            await save_history(user_uuid=user_uuid, history=history)

            # 推送最终答案
            await queue.put(json.dumps({"type": "answer", "text": assistant_reply}) + "\n")

        queue = asyncio.Queue()
        # 启动心跳和主逻辑
        heartbeat_task = asyncio.create_task(heartbeat_sender(queue))
        main_task = asyncio.create_task(main_logic(queue))

        try:
            while True:
                item = await queue.get()
                yield item
                if item.startswith('{"type": "answer"'):
                    break
        finally:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task

    return StreamingResponse(event_stream(), media_type='application/x-ndjson')

@router.post('/game/ask_chain')
async def api_ask_chain(request: ChatRequest):
    question = request.question
    user_token = request.user_token
    user = await get_user_llm_info(user_token=user_token)

    client = OpenAI(
        # api_key=user.get('api_key'),
        api_key=good_api_key,
        base_url=user.get('api_url')
    )

    async def event_stream():
        #心跳
        async def heartbeat_sender(queue):
            try:
                while True:
                    await queue.put(json.dumps({"type": "heartbeat"}) + "\n")
                    await asyncio.sleep(50)  # 心跳间隔时间
            except asyncio.CancelledError:
                pass
        #主任务
        async def main_logic(queue):
            try:
                # 第一次调用 API
                first_prompt = f"""【用户需求】：{question}"""
                # print(first_prompt)
                response_1 = await asyncio.to_thread(
                    client.chat.completions.create,
                    model='gpt-4o',
                    messages=[
                        {
                            "role": "system",
                            "content": """
                                【名称】
                                课堂游戏html规划
                                【操作指令】
                                1.需要规划出开始游戏、结束游戏、重置游戏的布局
                                2.尽可能将游戏运作细节展示到html，设计好html，css，JavaScript框架
                                3.重点在保证能使用的前提下规划JavaScript交互逻辑的健壮性，规划css色彩的变化
                                4.设计出可能要用到的JavaScript函数名
                                5.指出需要注意的代码板块
                                【规则】
                                1.只输出游戏具体的框架规划
                                2.不输出代码
                                【输出格式要求】
                                游戏名称:
                                XXX
                                游戏规则:
                                XXX
                                游戏代码框架规划:
                                XXX: 
                            """
                        },
                        {
                            "role": "user",
                            "content": first_prompt
                        }
                    ]
                )
                first_reply = response_1.choices[0].message.content
                # print(first_reply)z
                #获取名字和游戏规则
                pattern = r"游戏名称:\s*(.*?)\n\n游戏规则:\s*(.*?)\n\n"
                match = re.search(pattern, first_reply, re.S)

                if match:
                    game_name = match.group(1).strip()  # 提取游戏名称并去除多余空格
                    game_rules = match.group(2).strip()  # 提取游戏规则并去除多余空格

                #第二次api调用
                second_prompt = f"""\n【游戏规划】：{first_reply}【用户需求】：{question}"""

                # print(second_prompt)

                response_2 = await asyncio.to_thread(
                    client.chat.completions.create,
                    # model='gpt-4o-mini',
                    model='deepseek-reasoner',
                    messages=[
                        {
                            "role": "system",
                            "content":"""
                                【名称】
                                HTML游戏生成助手
                                【操作指令】
                                1.根据已经有规则和游戏内容素材生成html、css、JavaScript
                                2.使用HTML语言编写游戏规则和使用流程的展示页面，包括页面头部、主体内容以及交互操作的布局。
                                3.重点:必须包含用户提供的所有上课内容
                                【规则】
                                1.HTML代码格式必须符合规范以确保兼容性和可读性，同时需避免使用未支持的HTML标签。
                                2.必须针对教育场景设计页面样式和交互功能，避免与课堂活动无关的内容和操作。
                                3.注意:所有代码都放在一个html，结果返回完整的htmI代码
                                4.为了让游戏具有完整性生成的JavaScript逻辑一定要清晰
                                【格式要求】
                                游戏代码:
                                xxx 
                            """
                        },
                        {
                            "role": "user",
                            "content": second_prompt
                        }
                    ]
                )
                second_reply = response_2.choices[0].message.content
                reply = re.sub(r"<think>.*?</think>", "", second_reply, flags=re.DOTALL)
                # print(reply)

                compressed_reply = base64.b64encode(gzip.compress(reply.encode("utf-8"))).decode("utf-8")

                # 推送第二次调用的结果
                await queue.put(json.dumps({
                    "type": "answer",
                    "game_name": game_name or '',
                    "game_rules": game_rules or '',
                    "result": compressed_reply
                }) + "\n")

            except Exception as e:
                # 推送错误信息
                await queue.put(json.dumps({"type": "error", "text": str(e)}) + "\n")

        queue = asyncio.Queue()
        heartbeat_task = asyncio.create_task(heartbeat_sender(queue))
        main_task = asyncio.create_task(main_logic(queue))

        try:
            while True:
                item = await queue.get()
                yield item
                if item.startswith('{"type": "answer"'):
                    break
        finally:
            # 取消心跳任务
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task

    return StreamingResponse(event_stream(), media_type='application/x-ndjson')

@router.post('/game/askname')
async def api_ask_getname(request: ChatRequest):
    question = request.question
    user_token = request.user_token
    user = await get_user_llm_info(user_token=user_token)
    client = OpenAI(
        # api_key=user.get('api_key'),
        api_key=good_api_key,
        base_url=user.get('api_url')
    )
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model=user.get('model_name'),
        messages=[
            {"role": "user", "content": f"请给下面的代码游戏内容取一个名字，与教育相关，要求字数不超过10个字，直接生成名字不需要解释，生成名字放在最后一排且前面用双换行隔开，下面是代码内容:+{question}"}
        ]
    )
    assistant_reply = response.choices[0].message.content
    cleaned_reply = assistant_reply.lstrip("\n")
    return cleaned_reply

@router.post('/game/askrules')
async def api_ask_getaskrules(request: ChatRequest):
    question = request.question
    user_token = request.user_token
    user = await get_user_llm_info(user_token=user_token)
    client = OpenAI(
        # api_key=user.get('api_key'),
        api_key=good_api_key,
        base_url=user.get('api_url')
    )
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model=user.get('model_name'),
        messages=[
            {
                "role": "user",
                "content": f"""
                请根据下面的代码内容生成一份游戏说明书，说明书内容需包含以下部分：
                1. 游戏名称（从代码内容中提炼，字数不超过10个字）。
                2. 游戏规则（简要说明游戏的玩法和规则）。
                3. 游戏目标（说明玩家需要完成的目标）。
                4. 游戏操作说明（详细说明游戏的操作方式，如按键、交互等）。
                5. 注意事项（列出游戏中的注意事项或特殊规则）。

                【格式要求】：
                1. 使用清晰的标题结构（如“游戏名称：XXX”、“游戏规则：XXX”）。
                2. 说明书内容需通俗易懂，适合教育场景。
                3. 最后生成完整的说明书内容，直接输出，不需要解释。

                【代码内容】：
                {question}
                """
            }
        ]
    )
    assistant_reply = response.choices[0].message.content
    return assistant_reply
