from pydantic import BaseModel

class ChatHistorySchema(BaseModel):
    user_uuid: str
    chat_history: str

    class Config:
        from_attributes = True

class ChatRequest(BaseModel):
    question: str
    user_token: str


# class QuestionRequest(BaseModel):
#     question: str
#     user_token: str
