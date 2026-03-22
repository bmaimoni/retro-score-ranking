import asyncio
import pytest
from services.sse import SSEBroker


@pytest.fixture
def broker():
    return SSEBroker()


@pytest.mark.asyncio
async def test_subscriber_recebe_ping_inicial(broker):
    gen = broker.subscribe("pac-man")
    try:
        evento = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
        assert "ping" in evento or "data" in evento
    finally:
        await gen.aclose()


@pytest.mark.asyncio
async def test_publish_entrega_evento_para_subscriber(broker):
    gen = broker.subscribe("pac-man")
    try:
        # Consome o ping inicial
        await asyncio.wait_for(gen.__anext__(), timeout=1.0)
        # Publica evento
        await broker.publish("pac-man", "novo_registro", {"nick": "P1", "pontuacao": 999})
        evento = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
        assert "novo_registro" in evento
    finally:
        await gen.aclose()


@pytest.mark.asyncio
async def test_publish_nao_afeta_outro_slug(broker):
    gen_pac = broker.subscribe("pac-man")
    gen_gal = broker.subscribe("galaga")
    try:
        # Consome pings iniciais
        await asyncio.wait_for(gen_pac.__anext__(), timeout=1.0)
        await asyncio.wait_for(gen_gal.__anext__(), timeout=1.0)

        # Publica apenas para pac-man
        await broker.publish("pac-man", "novo_registro", {"nick": "P1"})

        # pac-man recebe
        evento_pac = await asyncio.wait_for(gen_pac.__anext__(), timeout=1.0)
        assert "novo_registro" in evento_pac

        # galaga NÃO deve receber — timeout esperado
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(gen_gal.__anext__(), timeout=0.1)
    finally:
        await gen_pac.aclose()
        await gen_gal.aclose()


@pytest.mark.asyncio
async def test_publish_sem_subscribers_nao_falha(broker):
    # Não deve levantar exceção
    await broker.publish("jogo-sem-subscribers", "evento", {"dado": 1})


@pytest.mark.asyncio
async def test_multiplos_subscribers_recebem_mesmo_evento(broker):
    gen1 = broker.subscribe("pac-man")
    gen2 = broker.subscribe("pac-man")
    try:
        # Consome pings
        await asyncio.wait_for(gen1.__anext__(), timeout=1.0)
        await asyncio.wait_for(gen2.__anext__(), timeout=1.0)

        await broker.publish("pac-man", "novo_registro", {"nick": "P1"})

        e1 = await asyncio.wait_for(gen1.__anext__(), timeout=1.0)
        e2 = await asyncio.wait_for(gen2.__anext__(), timeout=1.0)
        assert "novo_registro" in e1
        assert "novo_registro" in e2
    finally:
        await gen1.aclose()
        await gen2.aclose()


@pytest.mark.asyncio
async def test_evento_formatado_corretamente(broker):
    gen = broker.subscribe("pac-man")
    try:
        await asyncio.wait_for(gen.__anext__(), timeout=1.0)
        await broker.publish("pac-man", "novo_registro", {"nick": "P1", "pontuacao": 5000})
        evento = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
        assert "event:" in evento
        assert "data:" in evento
        assert "novo_registro" in evento
    finally:
        await gen.aclose()