"""Container health check for safe deployment modes."""

from __future__ import annotations

from silver_bot.config import ConfigError, load_config


def main() -> int:
    """Return healthy only when configuration is safe and non-live."""

    try:
        config = load_config()
    except ConfigError:
        return 2
    if config.live_trading:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
