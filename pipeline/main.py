from __future__ import annotations
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Ensure UTF-8 output on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from pipeline.orchestrator import run_pipeline


def main():
    if len(sys.argv) > 1:
        topic = " ".join(sys.argv[1:])
    else:
        topic = input("Enter video topic/query: ").strip()
        if not topic:
            topic = "Two anime idols practicing a duet on stage"

    asyncio.run(run_pipeline(topic))


if __name__ == "__main__":
    main()
