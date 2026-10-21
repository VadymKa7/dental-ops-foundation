"""Aggregate versioned business routers.

Health probes are not included here. They stay on the application root.
"""

from fastapi import APIRouter

from app.modules.users.router import router as users_router

api_router = APIRouter()
api_router.include_router(users_router)
