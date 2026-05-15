#!/usr/bin/env python3
from wsgiref.simple_server import make_server

from asr_app.config import env
from asr_app.routes import application


if __name__ == "__main__":
    port = int(env("PORT", "8789"))
    with make_server("0.0.0.0", port, application) as server:
        print(f"server_asr listening on http://127.0.0.1:{port}")
        server.serve_forever()
