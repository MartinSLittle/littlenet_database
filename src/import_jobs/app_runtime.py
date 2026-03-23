from __future__ import annotations

import os
from pathlib import Path
import sys


APP_DIR_NAME = "Littlenet Database"
DEFAULT_DB_NAME = "littlenet_database.sqlite3"


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
