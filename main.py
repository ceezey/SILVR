"""Repository entrypoint for the Silver Bot application."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from silver_bot.main import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
