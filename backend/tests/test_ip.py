import pytest
from unittest.mock import patch, MagicMock
from utils.ip import get_client_ip, hash_ip


# ── get_client_ip ─────────────────────────────────────────────────────────────

def _make_request(forwarded=None, client_host="127.0.0.1"):
    req = MagicMock()
    req.headers = {}
    if forwarded:
        req.headers = {"X-Forwarded-For": forwarded}
    req.client = MagicMock(host=client_host)
    return req


def test_usa_client_host_quando_sem_proxy():
    req = _make_request(client_host="192.168.1.1")
    assert get_client_ip(req) == "192.168.1.1"


def test_usa_primeiro_ip_do_forwarded():
    req = _make_request(forwarded="203.0.113.1, 10.0.0.1, 172.16.0.1")
    assert get_client_ip(req) == "203.0.113.1"


def test_strip_espaco_no_forwarded():
    req = _make_request(forwarded="  10.0.0.5  , 10.0.0.2")
    assert get_client_ip(req) == "10.0.0.5"


def test_sem_client_retorna_unknown():
    req = MagicMock()
    req.headers = {}
    req.client = None
    assert get_client_ip(req) == "unknown"


# ── hash_ip ───────────────────────────────────────────────────────────────────

def test_hash_retorna_string_hex():
    with patch("utils.ip.get_settings") as mock:
        mock.return_value.ip_hash_salt = "salt123"
        resultado = hash_ip("192.168.1.1")
    assert len(resultado) == 64
    assert all(c in "0123456789abcdef" for c in resultado)


def test_mesmo_ip_mesmo_hash():
    with patch("utils.ip.get_settings") as mock:
        mock.return_value.ip_hash_salt = "salt123"
        h1 = hash_ip("10.0.0.1")
        h2 = hash_ip("10.0.0.1")
    assert h1 == h2


def test_ips_diferentes_hashes_diferentes():
    with patch("utils.ip.get_settings") as mock:
        mock.return_value.ip_hash_salt = "salt123"
        h1 = hash_ip("10.0.0.1")
        h2 = hash_ip("10.0.0.2")
    assert h1 != h2


def test_salt_diferente_hash_diferente():
    """Garante que o salt realmente afeta o hash (não é decorativo)."""
    with patch("utils.ip.get_settings") as mock:
        mock.return_value.ip_hash_salt = "salt_a"
        h1 = hash_ip("10.0.0.1")

    with patch("utils.ip.get_settings") as mock:
        mock.return_value.ip_hash_salt = "salt_b"
        h2 = hash_ip("10.0.0.1")

    assert h1 != h2


def test_hash_nao_contem_ip_original():
    """O IP bruto não deve aparecer no hash — requisito LGPD."""
    with patch("utils.ip.get_settings") as mock:
        mock.return_value.ip_hash_salt = "qualquer"
        resultado = hash_ip("192.168.1.1")
    assert "192.168.1.1" not in resultado
