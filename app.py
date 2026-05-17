#!/usr/bin/env python3
import os
import subprocess
import sys
import time
from pathlib import Path
from wsgiref.simple_server import make_server

from config import env
from routes import application


ROOT = Path(__file__).resolve().parent
WATCH_SUFFIXES = {".py"}


def run_server():
    port = int(env("PORT", "8789"))
    with make_server("0.0.0.0", port, application) as server:
        print(f"server_asr listening on http://127.0.0.1:{port}")
        server.serve_forever()


def watched_mtimes():
    paths = []
    for path in ROOT.rglob("*"):
        if path.suffix in WATCH_SUFFIXES:
            # 排除 data, public, .git, .gemini, __pycache__
            if any(p in path.parts for p in ("data", "public", ".git", ".gemini", "__pycache__")):
                continue
            paths.append(path)
    return {
        str(path): path.stat().st_mtime
        for path in paths
        if path.exists() and path.is_file()
    }


def run_reloader():
    print("server_asr dev reload enabled")
    mtimes = watched_mtimes()
    child = None
    try:
        while True:
            if child is None or child.poll() is not None:
                env_vars = {**os.environ, "ASR_DEV_RELOAD_CHILD": "1", "ASR_NO_CACHE": "1"}
                child = subprocess.Popen([sys.executable, __file__], env=env_vars)
            time.sleep(.8)
            current = watched_mtimes()
            if current != mtimes:
                mtimes = current
                print("file change detected, restarting server_asr...")
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
                child = None
    except KeyboardInterrupt:
        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
        print("\nserver_asr dev reload stopped")


if __name__ == "__main__":
    if "--reload" in sys.argv and os.environ.get("ASR_DEV_RELOAD_CHILD") != "1":
        run_reloader()
    else:
        run_server()
