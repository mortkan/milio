#!/usr/bin/env python3
"""Punto de entrada de la Agenda.

Uso:
    python main.py                 # inicia en el host/puerto configurado
    python main.py --seed          # crea datos de ejemplo si la BD está vacía
    python main.py --reload        # recarga automática para desarrollo
    python main.py --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import argparse
import logging
import os

import uvicorn

from app.config import ensure_directories, get_settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Agenda personal")
    parser.add_argument("--host", help="Host de escucha (sobreescribe config.yaml)")
    parser.add_argument("--port", type=int, help="Puerto de escucha")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Recarga automática (desarrollo)",
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Carga datos de ejemplo si la base de datos está vacía",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.host:
        os.environ["AGENDA_HOST"] = args.host
    if args.port:
        os.environ["AGENDA_PORT"] = str(args.port)
    if args.seed:
        os.environ["AGENDA_SEED"] = "1"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ensure_directories()
    settings = get_settings()
    host = args.host or settings.server.host
    port = args.port or settings.server.port
    display_host = "localhost" if host in {"0.0.0.0", "::"} else host

    print()
    print(f"  {settings.app_name} · http://{display_host}:{port}")
    print(f"  API docs  → http://{display_host}:{port}/docs")
    print()

    uvicorn.run(
        "app.server:app",
        host=host,
        port=port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
