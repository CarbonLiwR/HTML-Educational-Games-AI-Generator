from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from backend.app.game.model.game_chat_history import Game_chat_history
from backend.app.game.model.game import Game
from backend.common import id_generation
from backend.database.db_mysql import async_db_session
from fastapi import Request
import pytz
from datetime import datetime


# 获取聊天记录
async def load_history(user_uuid: str) -> list:
    async with async_db_session() as db:
        result = await db.execute(select(Game_chat_history).where(Game_chat_history.user_uuid == user_uuid))
        chat_record = result.scalar_one_or_none()
        return chat_record.chat_history.split("\n") if chat_record else [
            "你是一个教育游戏开发助手，提问的人会向你提出需要开发游戏的领域和相关需求，你只需要传回游戏的html文件代码即可,不需要除了代码"
            "以外的其他任何内容，只需要代码部分\n"
        ]
    
#保存聊天记录
async def save_history(user_uuid: str, history: list):
    history_str = "\n".join(history)
    async with async_db_session() as db:
        result = await db.execute(select(Game_chat_history).where(Game_chat_history.user_uuid == user_uuid))
        chat_record = result.scalar_one_or_none()
        if chat_record:
            chat_record.chat_history = history_str
        else:
            db.add(Game_chat_history(user_uuid=user_uuid, chat_history=history_str))
        await db.commit()
    
#清空聊天记录
async def clear_chat_history(user_uuid: str):
    async with async_db_session() as db:
        result = await db.execute(select(Game_chat_history).where(Game_chat_history.user_uuid == user_uuid))
        chat_record = result.scalar_one_or_none()
        if chat_record:
            await db.delete(chat_record)
            await db.commit()
    
async def get_all_games() -> list[Game]:
    async with async_db_session() as db:
        result = await db.execute(select(Game))
        games = result.scalars().all()
        return games

async def get_game(game_id: int) -> Game | None:
    """
    根据 ID 获取游戏
    :param game_id: 游戏的 ID
    :return: 返回游戏对象或 None（如果游戏不存在）
    """
    async with async_db_session() as db:
        result = await db.execute(select(Game).where(Game.id == game_id))
        db_game = result.scalar_one_or_none()

        return db_game


# 创建游戏
async def saving_game(game_data: dict) -> Game:
    async with async_db_session() as db:
        # 检查是否已经存在具有相同 UUID 的游戏
        result = await db.execute(select(Game).where(Game.uuid == game_data["uuid"]))
        existing_game = result.scalar_one_or_none()

        if existing_game:
            # 如果 UUID 已存在，直接返回现有的游戏对象
            return existing_game

        # 如果 UUID 不存在，则创建新的游戏
        db_game = Game(**game_data)
        db.add(db_game)
        await db.commit()
        await db.refresh(db_game)
        return db_game


# 删除游戏
async def delete_game(game_uuid: str) -> bool:
    """
    根据 ID 删除游戏
    :param game_id: 游戏的 ID
    :return: 是否删除成功
    """
    async with async_db_session() as db:
        # 查询游戏是否存在
        result = await db.execute(select(Game).where(Game.uuid == game_uuid))
        db_game = result.scalar_one_or_none()

        if db_game is None:
            # 游戏不存在
            return False

        # 删除游戏
        await db.delete(db_game)
        await db.commit()
        return True

#修改名字
async def update_game_name(game_uuid: str, new_name: str) -> bool:
    """
    根据 UUID 修改游戏的名字
    :param game_uuid: 游戏的 UUID
    :param new_name: 新的名字
    :return: 是否修改成功
    """
    async with async_db_session() as db:
        # 查询游戏是否存在
        result = await db.execute(select(Game).where(Game.uuid == game_uuid))
        db_game = result.scalar_one_or_none()

        if db_game is None:
            # 游戏不存在
            return False

        # 更新游戏名字
        db_game.name = new_name
        await db.commit()
        await db.refresh(db_game)  # 刷新对象以确保返回最新数据
        return True
