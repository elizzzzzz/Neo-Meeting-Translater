from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local meeting interpreter demo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--mock", action="store_true", help="run without downloading model weights")
    args = parser.parse_args()
    uvicorn.run("meeting_interpreter.app:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
