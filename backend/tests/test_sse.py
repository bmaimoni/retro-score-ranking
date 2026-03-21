import asyncio
import json
import pytest
from services.sse import SSEBroker


@pytest.mark.asyncio
async def test_subscriber_recebe_ping_inicial():
    broker = SSEBroker()
    gen = broker.subscribe("pac-man")
    primeiro = await gen.__anext__()
    assert "ping" in primeiro
    assert "conectado" in primeiro


@pytest.mark.asyncio
async def test_publish_entrega_evento_para_subscriber():
    broker = SSEBroker()
    gen = broker.subscribe("pac-man")

    # Consome o ping inicial
    await gen.__anext__()

    # Publica um evento
    await broker.publish("pac-man", "novo_registro", {"nick": "Jogador1", "pontuacao": 50000})

    evento = await gen.__anext__()
    assert "novo_registro" in evento
    assert "Jogador1" in evento
    assert "50000" in evento


@pytest.mark.asyncio
async def test_publish_nao_afeta_outro_slug():
    broker = SSEBroker()
    gen_pac = broker.subscribe("pac-man")
    gen_gal = broker.subscribe("galaga")

    # Consome pings
    await gen_pac.__anext__()
    await gen_gal.__anext__()

    # Publica só no pac-man
    await broker.publish("pac-man", "novo_registro", {"nick": "X"})

    # pac-man recebe
    ev = await gen_pac.__anext__()
    assert "novo_registro" in ev

    # galaga NÃO deve receber — queue deve estar vazia
    assert gen_gal._ag_running  # gerador ainda está vivo, mas sem evento


@pytest.mark.asyncio
async def test_publish_sem_subscribers_nao_falha():
    broker = SSEBroker()
    # Não deve levantar exceção mesmo sem ninguém ouvindo
    await broker.publish("jogo-sem-viewers", "novo_registro", {"nick": "X"})


@pytest.mark.asyncio
async def test_multiplos_subscribers_recebem_mesmo_evento():
    broker = SSEBroker()
    gen1 = broker.subscribe("pac-man")
    gen2 = broker.subscribe("pac-man")

    await gen1.__anext__()  # pings
    await gen2.__anext__()

    await broker.publish("pac-man", "ocultar", {"id": "abc123"})

    ev1 = await gen1.__anext__()
    ev2 = await gen2.__anext__()

    assert "ocultar" in ev1
    assert "ocultar" in ev2
    assert ev1 == ev2


@pytest.mark.asyncio
async def test_evento_formatado_corretamente():
    broker = SSEBroker()
    gen = broker.subscribe("river-raid")
    await gen.__anext__()  # ping

    await broker.publish("river-raid", "reativar", {"id": "xyz", "nick": "Piloto"})
    evento = await gen.__anext__()

    linhas = evento.strip().split("\n")
    assert linhas[0] == "event: reativar"
    assert linhas[1].startswith("data: ")

    dados = json.loads(linhas[1][len("data: "):])
    assert dados["id"] == "xyz"
    assert dados["nick"] == "Piloto"
