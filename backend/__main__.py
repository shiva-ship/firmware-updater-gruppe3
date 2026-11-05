"""Startet den Server: ``python -m backend``."""

from __future__ import annotations

import logging
import sys

import uvicorn

from backend.config import get_settings
from backend.main import create_app


def main() -> int:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    if not settings.binds_loopback_only and not settings.tls_enabled:
        print(
            "Abbruch: Bindung an eine Nicht-Loopback-Adresse ist nur mit HTTPS erlaubt.\n"
            "Setzen Sie ASM_TLS_CERTFILE und ASM_TLS_KEYFILE oder verwenden Sie ASM_HOST=127.0.0.1.",
            file=sys.stderr,
        )
        return 2
    if not settings.binds_loopback_only and settings.allowed_host_list == ["127.0.0.1", "localhost"]:
        print("Hinweis: Für LAN-Zugriff muss ASM_ALLOWED_HOSTS den Hostnamen des Servers enthalten.", file=sys.stderr)

    scheme = "https" if settings.tls_enabled else "http"
    logging.getLogger("backend").info("ADS-TEC Security Manager läuft auf %s://%s:%d", scheme, settings.host, settings.port)

    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        # Sitzungszustand der KeePass-Datenbanken liegt im Prozessspeicher → genau ein Worker.
        workers=1,
        reload=False,
        proxy_headers=False,
        server_header=False,
        date_header=False,
        ssl_certfile=str(settings.tls_certfile) if settings.tls_enabled else None,
        ssl_keyfile=str(settings.tls_keyfile) if settings.tls_enabled else None,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
