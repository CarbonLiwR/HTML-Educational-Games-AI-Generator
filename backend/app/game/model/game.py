from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Game(Base):
    """
    游戏模型
    """
    __tablename__ = "game"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    uuid = Column(String(255), nullable=False)
    name = Column(String(255), nullable=True)
    url = Column(String(255), nullable=True)
    code = Column(Text, nullable=False)
    rules = Column(Text, nullable=False)
