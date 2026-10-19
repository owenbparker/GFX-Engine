"""Start the engine without a window:  python -m gfxengine

For the desktop app, run GFXEngine.exe (or python -m gfxengine.gui).
"""

import argparse
import time

from .app import Engine, start
from .config import Settings


def build_engine(args):
    settings = Settings()
    if args.port:
        settings.update({"http_port": args.port})
    return Engine(settings)


def add_arguments(parser):
    parser.add_argument("--port", type=int, help="web server port (saved to settings.json)")


def main():
    parser = argparse.ArgumentParser(description="SCC GFX Engine")
    add_arguments(parser)
    engine = build_engine(parser.parse_args())
    start(engine)
    print("  Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()


if __name__ == "__main__":
    main()
