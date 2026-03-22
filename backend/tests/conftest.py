import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main import app


# ── FakePool ──────────────────────────────────────────────────────────────────

class FakePool:
    def __init__(self):
        self.fetchval = AsyncMock(return_value=0)
        self.fetchrow = AsyncMock(return_value=None)
        self.fetch    = AsyncMock(return_value=[])
        self.execute  = AsyncMock(return_value="UPDATE 1")
        self._conn    = _FakeConn()
        self.acquire  = MagicMock(return_value=self._conn)

    def set_fetchrow(self, value): self.fetchrow = AsyncMock(return_value=value)
    def set_fetch(self, value):    self.fetch    = AsyncMock(return_value=value)
    def set_fetchval(self, value): self.fetchval = AsyncMock(return_value=value)


class _FakeConn:
    def __init__(self):
        self.fetchrow    = AsyncMock(return_value=None)
        self.fetch       = AsyncMock(return_value=[])
        self.execute     = AsyncMock(return_value="UPDATE 1")
        self.fetchval    = AsyncMock(return_value=0)
        self.transaction = MagicMock(return_value=_FakeTxn())

    async def __aenter__(self): return self
    async def __aexit__(self, *_): pass


class _FakeTxn:
    async def __aenter__(self): return self
    async def __aexit__(self, *_): pass


@pytest.fixture
def fake_pool():
    return FakePool()


# ── Cliente HTTP ──────────────────────────────────────────────────────────────

@pytest.fixture
async def client():
    from httpx import AsyncClient, ASGITransport
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


# ── Factories ─────────────────────────────────────────────────────────────────

def make_uuid():
    return str(uuid.uuid4())

def make_jogo(slug="pac-man", nome="Pac-Man", score_max=999990, ativo=True):
    return {"id": make_uuid(), "slug": slug, "nome": nome,
            "score_max": score_max, "ativo": ativo}

def make_entrada(nick="PLAYER1", pontuacao=50000, jogo_id=None,
                 no_ranking=True, superado=False, pendente=False,
                 foto_url="https://cdn.example.com/foto.jpg"):
    return {
        "id": make_uuid(), "jogo_id": jogo_id or make_uuid(),
        "nick": nick, "nick_norm": nick.lower().strip(),
        "pontuacao": pontuacao, "foto_url": foto_url,
        "no_ranking": no_ranking, "superado": superado, "pendente": pendente,
        "ip_hash": "abc123", "criado_em": "2024-01-01T00:00:00Z",
        "moderado_em": None, "moderado_por": None,
        "jogo_nome": "Pac-Man", "jogo_slug": "pac-man",
    }

def make_jpeg_bytes():
    return (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xd9")

def make_png_bytes():
    return (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
            b"\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
            b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
            b"\x00\x00\x00\x00IEND\xaeB`\x82")

def make_pdf_bytes():
    return b"%PDF-1.4 fake content that is definitely not an image"