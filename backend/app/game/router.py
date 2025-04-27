from fastapi import APIRouter
from backend.app.game.api.router import v1 as game_v1

route = APIRouter()

route.include_router(game_v1)
