from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.request_context import RequestContextMiddleware
from app.modules.api.v1.router import router as api_v1_router
from app.modules.reference.pack import PackRegistry, register_default_packs


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Talvrin API", version="0.1.0")

    # No endpoint reads this yet (P1 wires real connectors/calc specs into
    # it) — wired into app.state now so it's a live, inspectable part of
    # the running app rather than a module nothing ever instantiates.
    app.state.pack_registry = PackRegistry()
    register_default_packs(app.state.pack_registry)

    app.add_middleware(RequestContextMiddleware)
    if settings.environment != "production":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allow_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_exception_handlers(app)
    app.include_router(api_v1_router)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
