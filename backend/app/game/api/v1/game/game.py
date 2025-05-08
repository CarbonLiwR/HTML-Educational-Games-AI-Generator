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
                first_prompt = f"""【用户需求】：{question}"""
                # print(first_prompt)
                response_1 = await asyncio.to_thread(
                    client.chat.completions.create,
                    model='o1',
                    # model='gpt-4o',
                    messages=[
                        {
                            "role": "system",
                            "content": """
                            现在你是 HTML5 游戏规划专家，请根据用户需求，输出该游戏的核心规划，包含以下精简模块，并严格用下方结构化格式返回(不要多余文字):
                            1.教学背景与目标
                                教学主题:
                                教学目标:
                            2.页面布局与样式
                                标题样式(字号/颜色)
                                背景与配色
                                班级互动区(教师参数面板+成绩面板)
                            3.核心玩法与规则
                                目标说明
                                操作方式
                                计分与奖励
                                游戏规则需要保证完整性
                            4. 技术实现与架构
                                技术栈
                                模块划分(数据层/视图层/逻辑层)
                                数据流(用户操作一事件回调→状态更新一渲染)
                                兼顾EDGE的格式
                            5.数据导入
                                支持格式(txt/csv/json)
                                上传与验证
                            6.逻辑流程
                                启动流程:参数校验一加载一渲染
                                回合流程:点击一校验一更新一反馈
                            7.交互反馈与按钮
                                视觉/音效反馈
                                -“开始游戏”/“重新开始“按钮
                                
                            **特别注意点：游戏名称和游戏规则必须保证按照给定格式输出
                            
                            输出格式：
                            游戏名称：
                            XXX
                                
                            游戏规则：
                            XXX
                                
                            教学背景与目标:
                            教学主题:
                            教学目标:
                                
                            参考案例：
                            游戏名称：
                            数学贪吃蛇
                                
                            游戏规则：
                            玩家需要使用上下左右键控制贪吃蛇吃到特定的球
                                
                            页面布局与样式:
                                标题样式:
                                字号: "xx"
                                颜色: "#xxxxxx"
                                背景: "#xxxxxx"
                            互动区:
                                教师面板: ["倒计时","难度"]
                                成绩面板: ["个人得分","小组进度"]
                                
                            核心玩法与规则:
                                目标说明: "…"
                                操作方式: "…"
                                计分与奖励: "…"
                                
                            技术实现与架构:
                                技术栈: ["HTML5","CSS3","JavaScript"]
                                模块划分: ["数据层","视图层","逻辑层"]
                                数据流: "用户操作→回调→状态更新→渲染"
                                
                            数据导入:
                                格式: ["txt","csv","json"]
                                验证: "文件格式及内容校验流程"
                                
                            逻辑流程:
                                启动流程: "校验→加载→渲染"
                                回合流程: "点击→校验→更新→反馈"
                                
                            交互反馈与按钮:
                                反馈: ["点击高亮","正确/错误音效","消除特效"]
                                按钮: ["开始游戏","重新开始"]
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
                # 第二次api调用
                second_prompt = f"""\n【游戏规划】：{first_reply}【用户需求】：{question}"""
                # print(second_prompt)
                response_2 = await asyncio.to_thread(
                    client.chat.completions.create,
                    # model='deepseek-reasoner',
                    model='o1',
                    messages=[
                        {
                            "role": "system",
                            "content": """
                                【名称】
                                HTML游戏生成助手
                                【操作指令】
                                1.根据已经有规则和游戏内容素材生成html、css、JavaScript
                                2.使用HTML语言编写游戏规则和使用流程的展示页面，包括页面头部、主体内容以及交互操作的布局
                                3.重点:必须包含用户提供的所有上课内容
                                4.函数实现过程要解决规划中提到的重点问题

                                【规则】
                                1.HTML代码格式必须符合规范以确保兼容性和可读性，同时需避免使用未支持的HTML标签
                                2.注意:所有代码都放在一个html，结果返回完整的htmI代码
                                3.保证有20左右的函数完成游戏逻辑的实现，生成的函数要有健壮性
                                4.请保证有400行左右代码提供完整的逻辑保障，但不需要出现具体游戏规则
                                
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
                # print("游戏生成成功")

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
