import asyncio
import pytest
import asyncpg
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

# Garante que os imports do projeto funcionam a partir da raiz do backend
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main import app
from config import get_settings


# ── Pool mock ─────────────────────────────────────────────────────────────────

class FakePool:
    """Pool asyncpg simulado para testes unitários."""

    def __init__(self):
        self._rows: dict[str, list] = {}
        self.fetchval = AsyncMock(return_value=1)
        self.fetchrow = AsyncMock(return_value=None)
        self.fetch    = AsyncMock(return_value=[])
        self.execute  = AsyncMock(return_value="UPDATE 1")
        self.acquire  = MagicMock(return_value=_FakeConn())

    def set_fetchrow(self, value):
        self.fetchrow = AsyncMock(return_value=value)

    def set_fetch(self, value):
        self.fetch = AsyncMock(return_value=value)


class _FakeConn:
    """Contexto de conexão para simular pool.acquire()."""
    def __init__(self):
        self.fetchrow  = AsyncMock(return_value=None)
        self.fetch     = AsyncMock(return_value=[])
        self.execute   = AsyncMock(return_value="UPDATE 1")
        self.transaction = MagicMock(return_value=_FakeTxn())

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _FakeTxn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.fixture
def fake_pool():
    return FakePool()


# ── Cliente HTTP assíncrono ───────────────────────────────────────────────────

@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


# ── Helpers de arquivo ────────────────────────────────────────────────────────

def make_jpeg_bytes() -> bytes:
    """Retorna bytes mínimos de um JPEG válido (magic bytes corretos)."""
    return (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        + b"\xff\xd9"
    )


def make_png_bytes() -> bytes:
    """Retorna bytes mínimos de um PNG válido."""
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
        b"\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
        b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
