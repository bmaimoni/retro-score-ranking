"""
E-mail de convite de coadministração (ARENA_SPEC.md Fase F) — mesmo
provedor (Resend) e mesmo padrão de erro do magic link
(auth/service.py._enviar_email_magic_link), só que pra um destinatário
que pode nunca ter ouvido falar da plataforma antes (copy mais
explicativa que o e-mail de login).
"""
import httpx
import structlog

from config import get_settings

log = structlog.get_logger()

ROLE_LABEL = {"admin": "administradora", "moderador": "moderadora"}


async def enviar_email_convite(email: str, link: str, arena_nome: str, role: str) -> None:
    settings = get_settings()
    if not settings.resend_api_key:
        log.warning("convite_email_sem_resend_configurado", email=email)
        raise RuntimeError("Envio de e-mail não configurado (RESEND_API_KEY ausente)")

    papel = ROLE_LABEL.get(role, role)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.resend_from_email,
                "to": [email],
                "subject": f"Convite para coadministrar {arena_nome} — Canal3",
                "html": (
                    f"<p>Você foi convidado(a) para ser <strong>{papel}</strong> "
                    f"da Arena <strong>{arena_nome}</strong> no Canal3.</p>"
                    f'<p><a href="{link}">Clique aqui para aceitar o convite</a></p>'
                    f"<p>Se você não esperava este convite, pode ignorar este e-mail. "
                    f"O link expira em {settings.convite_ttl_days} dias.</p>"
                ),
            },
        )
        resp.raise_for_status()
