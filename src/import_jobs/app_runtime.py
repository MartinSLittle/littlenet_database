from __future__ import annotations

import json
import os
from pathlib import Path
import sys


APP_DIR_NAME = "Littlenet Database"
DEFAULT_DB_NAME = "littlenet_database.sqlite3"
CONFIG_FILE_NAME = "gui_config.json"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_user_data_dir() -> Path:
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / APP_DIR_NAME
        return Path.home() / "AppData" / "Local" / APP_DIR_NAME
    return Path.home() / ".local" / "share" / APP_DIR_NAME


def get_default_db_path() -> Path:
    if is_frozen():
        return get_user_data_dir() / DEFAULT_DB_NAME
    return get_project_root() / DEFAULT_DB_NAME


def get_config_path() -> Path:
    return get_user_data_dir() / CONFIG_FILE_NAME


def load_app_config() -> dict[str, object]:
    config_path = get_config_path()
    if not config_path.exists():
        return {}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def save_app_config(data: dict[str, object]) -> None:
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def load_last_db_path() -> tuple[Path, str | None]:
    default_path = get_default_db_path()
    config = load_app_config()
    raw_path = config.get("last_db_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return default_path, None

    candidate = Path(raw_path).expanduser()
    if candidate.exists():
        return candidate, None

    return default_path, (
        f"La ultima base guardada no existe: {candidate}. Se usa la ruta por defecto."
    )


def save_last_db_path(db_path: str | Path) -> None:
    path = Path(db_path).expanduser()
    config = load_app_config()
    config["last_db_path"] = str(path)
    save_app_config(config)
