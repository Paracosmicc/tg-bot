import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import router, PHOTO_DIR, VOICE_DIR


def create_app() -> FastAPI:
    app = FastAPI(
        title="Vaidehi Bot Control Panel API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS support for Vercel frontend and local development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount static assets so frontend can preview photos and play voice notes directly
    if os.path.exists(PHOTO_DIR):
        app.mount("/media/photos", StaticFiles(directory=PHOTO_DIR), name="photos")
    if os.path.exists(VOICE_DIR):
        app.mount("/media/voices", StaticFiles(directory=VOICE_DIR), name="voices")

    # Include routes
    app.include_router(router)

    return app


api_app = create_app()


async def run_web_server(tg_app, port: int = 8080, host: str = "0.0.0.0"):
    """
    Run FastAPI server with Uvicorn inside the same asyncio event loop as Telegram bot.
    """
    api_app.state.tg_app = tg_app
    config = uvicorn.Config(
        app=api_app,
        host=host,
        port=port,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)
    await server.serve()
