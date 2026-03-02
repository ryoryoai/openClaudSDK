"""Entry point: ``python -m openclaw``."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from openclaw.config import load_config
from openclaw.discord_adapter.bot import create_bot


def _run(args: argparse.Namespace) -> None:
    """Run the bot (default command)."""
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


def _install_daemon(args: argparse.Namespace) -> None:
    """Install OpenClaw as a system service."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    from openclaw.daemon.installer import DaemonInstaller

    installer = DaemonInstaller()
    installer.install()
    print("Daemon installed successfully.")


def _uninstall_daemon(args: argparse.Namespace) -> None:
    """Uninstall the OpenClaw system service."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    from openclaw.daemon.installer import DaemonInstaller

    installer = DaemonInstaller()
    installer.uninstall()
    print("Daemon uninstalled successfully.")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="openclaw",
        description="OpenClaw — Discord AI Agent powered by Claude Agent SDK",
    )
    subparsers = parser.add_subparsers(dest="command")

    # run (default)
    run_parser = subparsers.add_parser(
        "run", help="Start the Discord bot (default)"
    )
    run_parser.set_defaults(func=_run)

    # install-daemon
    install_parser = subparsers.add_parser(
        "install-daemon",
        help="Install OpenClaw as a user-level system service",
    )
    install_parser.set_defaults(func=_install_daemon)

    # uninstall-daemon
    uninstall_parser = subparsers.add_parser(
        "uninstall-daemon",
        help="Uninstall the OpenClaw system service",
    )
    uninstall_parser.set_defaults(func=_uninstall_daemon)

    args = parser.parse_args()

    # Default to 'run' if no subcommand is given (backward compatible)
    if args.command is None:
        args.func = _run

    args.func(args)


if __name__ == "__main__":
    main()
