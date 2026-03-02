"""Daemon installer for Linux (systemd --user) and macOS (launchd)."""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from openclaw.daemon.templates import LAUNCHD_PLIST, SYSTEMD_UNIT

logger = logging.getLogger(__name__)

SERVICE_NAME = "openclaw"
LAUNCHD_LABEL = "com.openclaw.agent"


class DaemonInstaller:
    """Install / uninstall OpenClaw as a user-level service."""

    def __init__(self, working_dir: str | Path | None = None) -> None:
        self._platform = platform.system().lower()
        self._working_dir = Path(working_dir or os.getcwd()).resolve()
        self._python_path = Path(sys.executable).resolve()

    def install(self) -> None:
        if self._platform == "linux":
            self._install_systemd()
        elif self._platform == "darwin":
            self._install_launchd()
        else:
            raise RuntimeError(f"Unsupported platform: {self._platform}")

    def uninstall(self) -> None:
        if self._platform == "linux":
            self._uninstall_systemd()
        elif self._platform == "darwin":
            self._uninstall_launchd()
        else:
            raise RuntimeError(f"Unsupported platform: {self._platform}")

    # --- systemd (Linux) ---

    def _systemd_unit_path(self) -> Path:
        config_dir = Path.home() / ".config" / "systemd" / "user"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / f"{SERVICE_NAME}.service"

    def _install_systemd(self) -> None:
        env_file = self._working_dir / ".env"
        exec_start = f"{self._python_path} -m openclaw"

        unit_content = SYSTEMD_UNIT.format(
            exec_start=exec_start,
            working_dir=self._working_dir,
            env_file=env_file if env_file.exists() else "",
        )

        unit_path = self._systemd_unit_path()
        unit_path.write_text(unit_content)
        logger.info("Wrote systemd unit: %s", unit_path)

        subprocess.run(
            ["systemctl", "--user", "daemon-reload"], check=True
        )
        subprocess.run(
            ["systemctl", "--user", "enable", SERVICE_NAME], check=True
        )
        subprocess.run(
            ["systemctl", "--user", "start", SERVICE_NAME], check=True
        )
        logger.info("Service %s installed and started", SERVICE_NAME)

    def _uninstall_systemd(self) -> None:
        subprocess.run(
            ["systemctl", "--user", "stop", SERVICE_NAME], check=False
        )
        subprocess.run(
            ["systemctl", "--user", "disable", SERVICE_NAME], check=False
        )
        unit_path = self._systemd_unit_path()
        if unit_path.exists():
            unit_path.unlink()
            logger.info("Removed systemd unit: %s", unit_path)
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"], check=True
        )
        logger.info("Service %s uninstalled", SERVICE_NAME)

    # --- launchd (macOS) ---

    def _launchd_plist_path(self) -> Path:
        agents_dir = Path.home() / "Library" / "LaunchAgents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        return agents_dir / f"{LAUNCHD_LABEL}.plist"

    def _install_launchd(self) -> None:
        log_dir = Path.home() / "Library" / "Logs" / SERVICE_NAME
        log_dir.mkdir(parents=True, exist_ok=True)

        path_env = os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")

        plist_content = LAUNCHD_PLIST.format(
            label=LAUNCHD_LABEL,
            python_path=self._python_path,
            working_dir=self._working_dir,
            path_env=path_env,
            log_dir=log_dir,
        )

        plist_path = self._launchd_plist_path()
        plist_path.write_text(plist_content)
        logger.info("Wrote launchd plist: %s", plist_path)

        subprocess.run(
            ["launchctl", "load", str(plist_path)], check=True
        )
        logger.info("Service %s installed and loaded", LAUNCHD_LABEL)

    def _uninstall_launchd(self) -> None:
        plist_path = self._launchd_plist_path()
        if plist_path.exists():
            subprocess.run(
                ["launchctl", "unload", str(plist_path)], check=False
            )
            plist_path.unlink()
            logger.info("Removed launchd plist: %s", plist_path)
        logger.info("Service %s uninstalled", LAUNCHD_LABEL)
