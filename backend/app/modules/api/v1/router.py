from fastapi import APIRouter

from app.modules.api.v1 import auth, instruments, issuers

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(issuers.router)
router.include_router(instruments.router)
