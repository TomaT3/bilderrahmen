"""Startpunkt: ein Prozess, zwei Ports (Rahmen-API öffentlich, Status nur im LAN)."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import uvicorn

from .app import create_app
from .config import load_config
from .photos import SynologyPhotos


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config = load_config(Path(os.environ.get("CONFIG_FILE", "/config/devices.yaml")))
    verify: bool | str = os.environ.get("SYNO_VERIFY_TLS", "true").lower() != "false"
    source = SynologyPhotos(
        os.environ["SYNO_URL"], os.environ["SYNO_USER"], os.environ["SYNO_PASSWORD"], verify=verify
    )
    frame_port = int(os.environ.get("FRAME_PORT", "8080"))
    status_port = int(os.environ.get("STATUS_PORT", "8081"))
    app = create_app(config, source, Path(os.environ.get("DATA_DIR", "/data")), status_port=status_port)

    async def serve() -> None:
        servers = [
            uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=port, proxy_headers=True, access_log=False))
            for port in (frame_port, status_port)
        ]
        await asyncio.gather(*(s.serve() for s in servers))

    asyncio.run(serve())


if __name__ == "__main__":
    main()
