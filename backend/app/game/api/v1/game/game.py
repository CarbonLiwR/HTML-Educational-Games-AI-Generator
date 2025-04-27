import contextlib
import json
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
    code: str

class GameDeleteRequest(BaseModel):
    uuid: str



class GameResponse(BaseModel):
    uuid:str
    name: Optional[str] = None
    url: Optional[str] = None
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

@router.post('/game/ask')
async def api_ask_stream(request: ChatRequest):
    question = request.question
    user_token = request.user_token
    user = await get_user_llm_info(user_token=user_token)
    user_uuid = user.get('user_uuid')
    client = OpenAI(
        api_key=user.get('api_key'),
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

@router.post('/game/askname')
async def api_ask_getname(request: ChatRequest):
    question = request.question
    user_token = request.user_token
    user = await get_user_llm_info(user_token=user_token)
    client = OpenAI(
        api_key=user.get('api_key'),
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