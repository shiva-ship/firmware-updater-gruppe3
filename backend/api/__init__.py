from fastapi import APIRouter

from . import auth, databases, setup

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(setup.router)
api_router.include_router(databases.router)


@api_router.get("/api/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}
