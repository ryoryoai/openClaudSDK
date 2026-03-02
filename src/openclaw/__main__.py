"""Entry point: ``python -m openclaw``."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from openclaw.config import load_config
from openclaw.discord_adapter.bot import create_bot


def main() -> None:
    # Allow running inside a Claude Code session (unset nesting guard)
    os.environ.pop("CLAUDECODE", None)

    # Load .env
    load_dotenv()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("openclaw")

    # Locate config file (default: config.yaml next to the package or cwd)
    config_path = Path(os.environ.get("OPENCLAW_CONFIG", "config.yaml"))
    logger.info("Loading config from %s", config_path)
    config = load_config(config_path)

    # Resolve Discord token
    token = os.environ.get("DISCORD_TOKEN") or config.discord.token
    if not token:
        logger.error(
            "DISCORD_TOKEN not set. Set it in .env or config.yaml (discord.token)"
        )
        sys.exit(1)

    # Create and run the bot
    bot = create_bot(config)
    logger.info("Starting OpenClaw bot...")
    bot.run(token, log_handler=None)  # log_handler=None to avoid duplicate logs


if __name__ == "__main__":
    main()
