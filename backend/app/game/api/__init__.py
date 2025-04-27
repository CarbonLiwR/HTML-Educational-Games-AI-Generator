from fastapi import APIRouter

from backend.app.game.api.v1.game import router as game_router
router = APIRouter()

router.include_router(game_router, tags=['游戏生成'])
