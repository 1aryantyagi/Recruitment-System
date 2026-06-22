"""ngrok tunnel for local development.

Real Twilio outbound calls require a publicly reachable webhook URL — Twilio
rejects `http://localhost:...` answer/status callbacks with error 21205. When
`NGROK_ENABLED=true`, we open an ngrok tunnel to the backend port on startup and
repoint `settings.backend_base_url` at the public URL, so the answer/status
callbacks built in the screening flow resolve to a reachable host.

Best-effort: if ngrok is unavailable the app still boots (Twilio then falls back
to mock mode), consistent with the graceful-degradation design in config.py.
"""
from __future__ import annotations

from urllib.parse import urlparse

from app.config import settings
from app.core.logging import get_logger

log = get_logger("tunnel")

_tunnel = None


def _backend_port(default: int = 8000) -> int:
    try:
        port = urlparse(settings.backend_base_url).port or default
        log.debug("tunnel.backend_port", port=port)
        return port
    except Exception:
        log.debug("tunnel.backend_port", port=default, fallback=True)
        return default


def start_tunnel() -> str | None:
    """Open an ngrok tunnel to the backend port and point `backend_base_url`
    at the public URL. No-op (returns None) when disabled or unavailable."""
    global _tunnel
    log.info("tunnel.start.begin")
    if not settings.ngrok_enabled:
        log.info("tunnel.start.noop", reason="ngrok_disabled")
        return None
    try:
        from pyngrok import conf, ngrok

        if settings.ngrok_authtoken:
            conf.get_default().auth_token = settings.ngrok_authtoken
        port = _backend_port()
        _tunnel = ngrok.connect(addr=port, proto="http")
        public_url = _tunnel.public_url
        # Prefer https so Twilio signature validation matches the callback scheme.
        if public_url.startswith("http://"):
            public_url = "https://" + public_url[len("http://"):]
        # Pin the Gmail OAuth redirect to the stable local URL before repointing
        # backend_base_url at the tunnel: that callback is hit by the admin's
        # local browser, and the free-plan ngrok host changes every restart, so
        # tying it to the tunnel would break the registered redirect each boot.
        if not settings.oauth_redirect_base_url:
            settings.oauth_redirect_base_url = settings.backend_base_url
        settings.backend_base_url = public_url.rstrip("/")
        log.info("ngrok_tunnel_started", public_url=settings.backend_base_url, port=port)
        log.info("tunnel.start.end", public_url=settings.backend_base_url, port=port)
        return settings.backend_base_url
    except Exception as exc:
        log.warning("ngrok_tunnel_failed", error=str(exc), exc_info=True)
        return None


def stop_tunnel() -> None:
    global _tunnel
    log.info("tunnel.stop.begin")
    if _tunnel is None:
        log.info("tunnel.stop.noop", reason="no_tunnel")
        return
    public_url = getattr(_tunnel, "public_url", None)
    try:
        from pyngrok import ngrok

        ngrok.disconnect(_tunnel.public_url)
        ngrok.kill()
        log.info("tunnel.stop.end", public_url=public_url)
    except Exception as exc:
        log.warning("ngrok_tunnel_stop_failed", error=str(exc), exc_info=True)
    finally:
        _tunnel = None
