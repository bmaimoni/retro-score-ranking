import asyncio
import json
from collections import defaultdict
from typing import AsyncGenerator
import structlog

log = structlog.get_logger()


class SSEBroker:
    """
    Gerencia conexões SSE ativas por slug de jogo.

    Cada cliente conectado ao ranking de um jogo recebe um asyncio.Queue.
    Ao publicar um evento, todos os queues daquele jogo são notificados.
    Conexões mortas são limpas automaticamente quando o gerador encerra.
    """

    def __init__(self) -> None:
        # slug -> set de queues ativas
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)

    async def subscribe(self, slug: str) -> AsyncGenerator[str, None]:
        """
        Generator que produz eventos SSE para um cliente.
        Deve ser usado como response do endpoint SSE.
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._subscribers[slug].add(queue)
        log.info("sse_subscribe", slug=slug, total=len(self._subscribers[slug]))

        try:
            # Envia ping inicial para confirmar conexão
            yield _format_event("ping", {"status": "conectado"})

            while True:
                try:
                    # Aguarda próximo evento com timeout para detectar clientes mortos
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield event
                except asyncio.TimeoutError:
                    # Keepalive: mantém a conexão viva em proxies que fecham idle
                    yield ": keepalive\n\n"
        finally:
            self._subscribers[slug].discard(queue)
            log.info("sse_unsubscribe", slug=slug, total=len(self._subscribers[slug]))

    async def publish(self, slug: str, tipo: str, dados: dict) -> None:
        """
        Envia um evento para todos os clientes conectados ao slug.
        Tipos: novo_registro | ocultar | reativar
        """
        if slug not in self._subscribers:
            return

        event = _format_event(tipo, dados)
        mortos = set()

        for queue in self._subscribers[slug]:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Cliente lento — remove para não bloquear os demais
                mortos.add(queue)

        for queue in mortos:
            self._subscribers[slug].discard(queue)

        log.info("sse_publish", slug=slug, tipo=tipo, clientes=len(self._subscribers[slug]))


def _format_event(tipo: str, dados: dict) -> str:
    return f"event: {tipo}\ndata: {json.dumps(dados, default=str)}\n\n"


# Instância global compartilhada pela aplicação
broker = SSEBroker()
