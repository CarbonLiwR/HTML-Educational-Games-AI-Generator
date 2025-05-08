import asyncio
import base64
import contextlib
import gzip
import json
import re
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from openai import OpenAI
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from backend.app.game.schema.game_chat_history_schemas import ChatRequest
from backend.app.game.service.game_service import load_history, save_history, get_game, get_all_games, saving_game, \
    delete_game, update_game_name
from backend.app.game.service.getuserinfo import get_user_llm_info

router = APIRouter()

max_history_length = 50


# 定义 Pydantic 模型
class Game(BaseModel):
    uuid: str
    name: Optional[str] = None
    url: Optional[str] = None
    rules: Optional[str] = None
    code: str


class GameDeleteRequest(BaseModel):
    uuid: str


class GameResponse(BaseModel):
    uuid: str
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
async def game_name_update(uuid: str, request: UpdateGameNameRequest):
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
        # 心跳
        async def heartbeat_sender(queue):
            try:
                while True:
                    await queue.put(json.dumps({"type": "heartbeat"}) + "\n")
                    await asyncio.sleep(50)  # 心跳间隔时间
            except asyncio.CancelledError:
                pass

        # 主任务
        async def main_logic(queue):
            try:
                # 第一次调用 API
                first_prompt = f"""【生成需求】：{question}"""
                # print(first_prompt)
                response_1 = await asyncio.to_thread(
                    client.chat.completions.create,
                    model='deepseek-v3',
                    # model='gpt-4o',
                    messages=[
                        {
                            "role": "system",
                            "content": """
                            请你作为一名资深教育游戏策划，你需要先根据用户需求指定具体教育场景，再根据教学的需求，输出一份完整的教育游戏设计文档，要求分块清晰、覆盖以下要素：
                            
                            {页面整体布局与样式}
                            1. 页面标题：网页顶端显示游戏名称（字体、字号、颜色说明）。  
                            2. 背景风格：指定背景颜色或渐变色、背景图案或主题插画。  
                            3. 布局区域：说明页面主要分几大区域（游戏画布／单词区／信息栏／操作按钮），并标出每块的相对位置和尺寸比例。  
                            4. 装饰元素：在页面哪些位置放置表情、图标或动效，提升趣味性。
                            
                            {核心玩法与交互}
                            1. 游戏主题：简要背景故事或玩法比喻。  
                            2. 操作方式：玩家点击、拖拽、键盘或触摸的具体交互。  
                            3. 胜负条件：明确什么情况下挑战成功、什么情况下挑战失败。  
                            4. 得分系统：基本计分规则，连对/连错如何增减分，最大分数或时间奖励。  
                            5. 难度递增：关卡数或无尽模式的动态难度变化说明（速度、数量、复杂度等）。
                            
                            {道具／元素设定}
                            1. 核心元素：列出所有游戏元素（如英文单词按钮、中文单词按钮、道具、障碍）。  
                            2. 元素效果：每个元素的行为和特效（点击、消除、碰撞、消失）。  
                            3. 特殊交互：语音发音（点击英文单词时）、错误提示音、胜利特效（烟花、动画）等。
                            
                            {UI 信息与提示}
                            1. 倒计时设置：输入框+确认按钮的交互流程，倒计时结束触发的提示。  
                            2. 分数/生命/关卡面板：分别显示哪些数值，更新频率。  
                            3. 开始/暂停/重新开始：对应按钮样式、位置和状态切换逻辑。  
                            4. 弹窗提示：挑战成功、挑战失败、重新开始确认等文字和动画效果。

                            输出格式：
                            游戏名称：
                            XXX
                                
                            游戏规则：
                            XXX
                                
                            页面整体布局与样式：
                            XXX
                                
                            核心玩法与交互：
                            XXX
                                
                            道具／元素设定：
                            XXX
                                
                            UI 信息与提示：
                            XXX
                            """
                        },
                        {
                            "role": "user",
                            "content": first_prompt
                        }
                    ]
                )
                first_reply = response_1.choices[0].message.content
                first_reply = re.sub(r'#', '', first_reply)
                # first_reply = re.sub(r"yaml|YAML|```", "", first_reply, flags=re.IGNORECASE)
                first_reply = first_reply.strip()

                pattern = r"游戏名称[:：]\s*(.*?)\n+游戏规则[:：]\s*(.*?)\n+"
                match = re.search(pattern, first_reply, re.S)

                if match:
                    game_name = match.group(1).strip() if match.group(1) else ""
                    game_rules = match.group(2).strip() if match.group(2) else ""
                    # print("游戏名称:", game_name)
                    # print("游戏规则:", game_rules)
                else:
                    print("未找到匹配的游戏名称和规则")
                    # print(first_reply)
                    return
                mid_prompt = f"""【第1步的设计文档内容】：{first_reply}"""
                # print(first_prompt)
                response_mid = await asyncio.to_thread(
                    client.chat.completions.create,
                    model='deepseek-v3',
                    # model='gpt-4o',
                    # model='o1',
                    messages=[
                        {
                            "role": "system",
                            "content": """
                               基于第 1 步的设计文档，请生成一个单文件 HTML 游戏的**骨架代码**，保持最小化实现，不包含具体逻辑，但要能直接在浏览器打开且不报错。要求： {HTML 结构} - DOCTYPE、<html>、<head>、<body> 三段式框架 - 在<head> 内嵌 <style>，声明所有页面区域的容器（如 #header, #game-area, #info-panel, #controls）和必要的 class 占位。 {CSS 占位} - 为每个大区块写基本布局（flex/grid），尺寸、颜色注释 - 按钮、输入框、标题的 class/id 声明，不写具体样式，仅写注释提示。 {JavaScript 架构} - 在 <body> 底部内嵌 <script> - 定义全局变量与 state（如 `let gameState = 'init'`、`let score = 0`、`let timer = null`） - 占位函数：`init()`, `startGame()`, `update()`, `render()`, `resetGame()`, `bindEvents()` - 游戏循环框架：`function loop(){ requestAnimationFrame(loop); update(); render(); }` - 事件监听占位：`document.getElementById('start-btn').addEventListener('click', …)` 请保证这份骨架能在控制台无报错，仅呈现空白布局与按钮／输入框等静态元素。
                            """
                        },
                        {
                            "role": "user",
                            "content": mid_prompt
                        }
                    ]
                )
                mid_reply = response_mid.choices[0].message.content
                # 第二次api调用
                second_prompt = f"""【骨架代码】：{mid_reply}"""
                # print(second_prompt)
                response_2 = await asyncio.to_thread(
                    client.chat.completions.create,
                    model='deepseek-reasoner',
                    # model='o1',
                    # model='gpt-4o',
                    messages=[
                        {
                            "role": "system",
                            "content": """
                                请在骨架代码基础上补全所有前端逻辑，实现一个可用的单文件 HTML 游戏。要点： 1. 渲染动态元素（如按钮、画布、倒计时、分数）。 2. 交互响应：用户点击/输入触发逻辑（计时、选择、匹配等）。 3. 音效与特效：按需播放音频、动画、提示。 4. 游戏流程：开始、进行、胜负判定、重置。 5. 性能与清理：移除已用元素、避免内存泄漏。 6. 注释与可配置：对主要函数、配置项添加说明，方便调整和扩展。 一次性输出可在主流浏览器中直接运行的完整单文件 HTML 代码。
                            """
                        },
                        {
                            "role": "user",
                            "content": second_prompt
                        }
                    ]
                )
                second_reply = response_2.choices[0].message.content
                # print(second_reply)
                cut_think_reply = re.sub(r"<think>.*?</think>", "", second_reply, flags=re.DOTALL)
                cut_html_reply = re.search(r"<html.*?>.*?</html>", cut_think_reply, flags=re.DOTALL)
                reply = cut_html_reply.group(0)
                # print(reply)
                compressed_reply = base64.b64encode(gzip.compress(reply.encode("utf-8"))).decode("utf-8")
                chunk_size = 512
                reply_chunks = [compressed_reply[i:i + chunk_size] for i in range(0, len(compressed_reply), chunk_size)]
                total_chunks = len(reply_chunks)

                for chunk_id, chunk in enumerate(reply_chunks):
                    chunk_data = {
                        "type": "answer_chunk",
                        "chunk_id": chunk_id,
                        "total_chunks": total_chunks,
                        "game_name": game_name if chunk_id == 0 else None,  # 仅在第一个块发送游戏名称
                        "game_rules": game_rules if chunk_id == 0 else None,  # 仅在第一个块发送游戏规则
                        "data": chunk  # 直接发送切块后的 Base64 数据
                    }
                    # print("chunk_id:", chunk_id)

                    # 发送数据块
                    await queue.put(json.dumps(chunk_data) + "\n")
                    # 发送结束标识
                await queue.put(json.dumps({"type": "end"}) + "\n")
                print("游戏生成成功")

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
                if item.startswith('{"type": "end"'):
                    break
        finally:
            # 取消心跳任务
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task

    return StreamingResponse(event_stream(), media_type='application/x-ndjson')


class OptimizeGameRequest(BaseModel):
    question: str
    code: str
    user_token: str


@router.post('/game/optimize')
async def api_optimize(request: OptimizeGameRequest):
    question = request.question
    code = request.code
    user_token = request.user_token
    user = await get_user_llm_info(user_token=user_token)

    client = OpenAI(
        # api_key=user.get('api_key'),
        api_key=good_api_key,
        base_url=user.get('api_url')
    )

    async def event_stream():
        # 心跳
        async def heartbeat_sender(queue):
            try:
                while True:
                    await queue.put(json.dumps({"type": "heartbeat"}) + "\n")
                    await asyncio.sleep(50)  # 心跳间隔时间
            except asyncio.CancelledError:
                pass

        # 主任务
        async def main_logic(queue):
            try:
                # 第一次调用 API
                first_prompt = f"""【需要优化的代码】：{code} 【用户的需求】:{question}"""
                # print(first_prompt)
                response = await asyncio.to_thread(
                    client.chat.completions.create,
                    # model='gpt-4o',
                    model='o1',
                    messages=[
                        {
                            "role": "system",
                            "content": """
                                在保持整体代码不变的情况下，根据下面的代码内容和用户需求优化代码，优化后返回一个HTML：
                                
                                【完整游戏代码】：
                            """
                        },
                        {
                            "role": "user",
                            "content": first_prompt
                        }
                    ]
                )
                reply = response.choices[0].message.content
                # print(reply)
                # print("回复完成")
                game_name = await api_ask_getname(request=ChatRequest(question=reply, user_token=user_token))
                # print(game_name)
                game_rules = await api_ask_getaskrules(request=ChatRequest(question=reply, user_token=user_token))
                # print(game_rules)
                compressed_reply = base64.b64encode(gzip.compress(reply.encode("utf-8"))).decode("utf-8")
                # print(compressed_reply)

                chunk_size = 512  # 每块大小
                reply_chunks = [compressed_reply[i:i + chunk_size] for i in range(0, len(compressed_reply), chunk_size)]
                total_chunks = len(reply_chunks)

                for chunk_id, chunk in enumerate(reply_chunks):
                    chunk_data = {
                        "type": "answer_chunk",
                        "chunk_id": chunk_id,
                        "total_chunks": total_chunks,
                        "game_name": game_name if chunk_id == 0 else None,  # 仅��第一个块发送游戏名称
                        "game_rules": game_rules if chunk_id == 0 else None,  # 仅在第一个块发送游戏规则
                        "data": chunk  # 直接发送切块后的 Base64 数据
                    }

                    # 发送数据块
                    await queue.put(json.dumps(chunk_data) + "\n")

                await queue.put(json.dumps({"type": "end"}) + "\n")
                print("游戏优化成功")
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
    # user = await get_user_llm_info(user_token=user_token)
    client = OpenAI(
        # api_key=user.get('api_key'),
        api_key=good_api_key,
        # base_url=user.get('api_url')
        base_url="https://api.rcouyi.com/v1"
    )
    response = await asyncio.to_thread(
        client.chat.completions.create,
        # model=user.get('model_name'),
        model="gpt-4o-mini",
        messages=[
            {"role": "user",
             "content": f"请给下面的代码游戏内容取一个名字，与教育相关，要求字数不超过10个字，直接生成名字不需要解释，不要md格式，纯文字输出，下面是代码内容:{question}"}
        ]
    )
    assistant_reply = response.choices[0].message.content
    cleaned_reply = assistant_reply.lstrip("\n")
    return cleaned_reply


@router.post('/game/askrules')
async def api_ask_getaskrules(request: ChatRequest):
    question = request.question
    user_token = request.user_token
    # user = await get_user_llm_info(user_token=user_token)
    client = OpenAI(
        # api_key=user.get('api_key'),
        api_key=good_api_key,
        base_url="https://api.rcouyi.com/v1"
        # base_url=user.get('api_url')
    )
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model="gpt-4o-mini",
        # model=user.get('model_name'),
        messages=[
            {
                "role": "user",
                "content": f"""
                请根据下面的代码内容生成一份游戏说明书，说明书内容需包含以下部分：
                1.游戏规则（简要说明游戏的玩法和规则）。
                2.游戏目标（说明玩家需要完成的目标）。
                3.游戏操作说明（详细说明游戏的操作方式，如按键、交互等）。

                【格式要求】：
                1. 使用清晰的标题结构。
                2. 说明书内容需通俗易懂，适合教育场景。
                3. 最后生成完整的说明书内容，直接输出，不需要解释。
                4. 说明书内容从简，不要使用任何markdown格式，纯文字返回,字数控制在五十字以内。

                【代码内容】：
                {question}
                """
            }
        ]
    )
    assistant_reply = response.choices[0].message.content
    return assistant_reply
