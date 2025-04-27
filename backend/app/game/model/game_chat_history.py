from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, Text

Base = declarative_base()


class Game_chat_history(Base):
    __tablename__ = "game_chat_history"
    id = Column(Integer, primary_key=True, index=True ,autoincrement=True)
    user_uuid = Column(Text)
    chat_history = Column(Text)
