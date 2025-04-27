#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from fastapi import APIRouter

from backend.app.game.api.v1.game import game_router


v1 = APIRouter()


v1.include_router(game_router)