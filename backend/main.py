import structlog
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import get_settings
from utils.db import get_pool, close_pool
from routers import upload, ranking, jogos, admin

# ── Logging estruturado ───────────────────────────────────────────────────────
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)
logging.basicConfig(level=logging.INFO)


# ── Lifecycle ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: inicializa pool de conexões
    await get_pool()
    structlog.get_logger().info("app_startup", env=get_settings().environment)
    yield
    # Shutdown: fecha pool graciosamente
    await close_pool()
    structlog.get_logger().info("app_shutdown")


# ── Aplicação ─────────────────────────────────────────────────────────────────
settings = get_settings()

app = FastAPI(
    title="Retro Score Ranking API",
    description="Backend para eventos de videogame retrô — C4 v1.0",
    version="1.0.0",
    # Desabilita docs em produção
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(upload.router)
app.include_router(ranking.router)
app.include_router(jogos.router)
app.include_router(admin.router)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["infra"])
async def health():
    pool = await get_pool()
    await pool.fetchval("SELECT 1")
    return {"status": "ok", "env": settings.environment}
