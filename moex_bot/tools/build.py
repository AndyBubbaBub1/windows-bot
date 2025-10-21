"""Сценарий сборки автономных пакетов (PyInstaller/Docker)."""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List

logger = logging.getLogger(__name__)


def _check_program(name: str) -> bool:
    return shutil.which(name) is not None


def build_standalone(
    *,
    entry: str = "moex_bot.run_server:main",
    icon: str | None = None,
    extra_data: Iterable[str] | None = None,
    dist_dir: str | Path = "dist",
) -> Path:
    """Собирает автономный ``.exe`` через PyInstaller.

    Возвращает путь к каталогу сборки.  Если PyInstaller не установлен,
    возбуждает ``RuntimeError`` с подсказкой по установке.
    """

    try:
        import PyInstaller.__main__ as pyinstaller  # type: ignore
    except Exception as exc:  # pragma: no cover - зависит от окружения
        raise RuntimeError(
            "PyInstaller не найден. Установите его командой 'pip install pyinstaller'."
        ) from exc

    module, func = entry.split(":", 1)
    script = Path("build_launcher.py")
    script.write_text(
        """
import importlib

module, func = "{module}", "{func}"
fn = getattr(importlib.import_module(module), func)
fn()
""".format(
            module=module, func=func
        ),
        encoding="utf-8",
    )

    cmd: List[str] = [
        "--onefile",
        "--name",
        "moex-bot",
        "--distpath",
        str(dist_dir),
        str(script),
    ]
    if icon:
        cmd.extend(["--icon", icon])
    for data in extra_data or []:
        cmd.extend(["--add-data", data])

    logger.info("Запуск PyInstaller с аргументами: %s", " ".join(cmd))
    pyinstaller.run(cmd)
    script.unlink(missing_ok=True)
    return Path(dist_dir) / "moex-bot.exe"


def build_docker(tag: str = "moex-bot:latest") -> None:
    """Собирает Docker-образ из ``moex_bot/Dockerfile``."""

    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"
    project_root = dockerfile.parent
    if not dockerfile.exists():
        raise FileNotFoundError("Dockerfile не найден")
    if not _check_program("docker"):
        raise RuntimeError("Docker не установлен или недоступен в PATH")
    cmd = ["docker", "build", "-t", tag, str(project_root)]
    logger.info("Выполняем %s", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Сборка автономных пакетов MOEX Bot")
    parser.add_argument("command", choices=["exe", "docker"], help="тип сборки")
    parser.add_argument("--entry", default="moex_bot.run_server:main", help="точка входа")
    parser.add_argument("--tag", default="moex-bot:latest", help="тег Docker-образа")
    parser.add_argument("--dist", default="dist", help="каталог для PyInstaller")
    parser.add_argument("--icon", default=None, help="путь к иконке .ico")
    args = parser.parse_args(list(argv) if argv is not None else None)

    logging.basicConfig(level=logging.INFO)

    try:
        if args.command == "exe":
            build_standalone(entry=args.entry, dist_dir=args.dist, icon=args.icon)
            logger.info("EXE собран в %s", args.dist)
        else:
            build_docker(tag=args.tag)
            logger.info("Docker-образ %s готов", args.tag)
    except Exception as exc:  # pragma: no cover - вывод для пользователя
        logger.error("Сборка прервана: %s", exc)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - прямой запуск
    sys.exit(main())
