from fastapi import APIRouter

from app.modules.api.v1 import instruments, issuers

router = APIRouter(prefix="/api/v1")
router.include_router(issuers.router)
router.include_router(instruments.router)
