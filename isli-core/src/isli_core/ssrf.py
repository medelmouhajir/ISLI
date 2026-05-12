import ipaddress
from urllib.parse import urlparse

from httpx import AsyncClient, Request

DEFAULT_BLOCKLIST = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "169.254.0.0/16",
    "fc00::/7",
    "fe80::/10",
}


class SSRFBlockedError(Exception):
    def __init__(self, url: str, reason: str):
        self.url = url
        self.reason = reason
        super().__init__(f"SSRF blocked: {url} ({reason})")


def _is_private_ip(host: str) -> bool:
    try:
        addr = ipaddress.ip_address(host)
        return addr.is_private or addr.is_loopback or addr.is_link_local
    except ValueError:
        return False


def _matches_blocklist(host: str, blocklist: set[str]) -> bool:
    for entry in blocklist:
        if "/" in entry:
            try:
                network = ipaddress.ip_network(entry, strict=False)
                addr = ipaddress.ip_address(host)
                if addr in network:
                    return True
            except ValueError:
                continue
        elif host == entry:
            return True
    return False


def validate_url(url: str, blocklist: set[str] | None = None) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise SSRFBlockedError(url, "Non-HTTP scheme")
    host = parsed.hostname
    if host is None:
        raise SSRFBlockedError(url, "Missing hostname")
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        raise SSRFBlockedError(url, "Localhost reference")
    if _is_private_ip(host):
        raise SSRFBlockedError(url, "Private IP")
    bl = blocklist or DEFAULT_BLOCKLIST
    if _matches_blocklist(host, bl):
        raise SSRFBlockedError(url, "Host in blocklist")


class SandboxedAsyncClient(AsyncClient):
    """httpx.AsyncClient that blocks SSRF targets before every request."""

    def __init__(self, blocklist: set[str] | None = None, **kwargs):
        super().__init__(**kwargs)
        self._blocklist = blocklist or DEFAULT_BLOCKLIST.copy()

    async def send(self, request: Request, **kwargs):
        validate_url(str(request.url), self._blocklist)
        return await super().send(request, **kwargs)
