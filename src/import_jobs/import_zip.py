from __future__ import annotations

import argparse
import logging
import mimetypes
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from extractor import (
    GENERIC_CASE_FOLDERS,
    infer_repair_data,
    normalize_text,
    safe_read_docx_text,
    safe_read_text,
)
from schema import (
    REPAIR_STATUS_RECEIVED,
    add_multimedia,
    connect_sqlite,
    create_reparacion,
    upsert_client,
    upsert_equipo,
)


TEXT_EXTENSIONS = {".txt", ".docx"}


@dataclass
class ImportStats:
    clients: int = 0
    equipment: int = 0
    repairs: int = 0
    multimedia: int = 0
    errors: int = 0


def today_iso() -> str:
    return datetime.now().date().isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Importa un ZIP de trabajos tecnicos a SQLite.")
    parser.add_argument("--zip", required=True, help="Ruta al archivo ZIP a importar.")
    parser.add_argument("--db", default="littlenet_database.sqlite3", help="Ruta al archivo SQLite.")
    parser.add_argument("--workspace", default="workspace", help="Carpeta controlada de descompresion.")
    parser.add_argument("--logs-dir", default="logs", help="Carpeta para logs de importacion.")
    return parser.parse_args()


def setup_logger(log_file: Path) -> logging.Logger:
    logger = logging.getLogger(f"import_zip_{datetime.now().timestamp()}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger


def safe_extract_zip(zip_path: Path, workspace_dir: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    extraction_dir = workspace_dir / f"import_{stamp}"
    extraction_dir.mkdir(parents=True, exist_ok=False)

    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            member_path = Path(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError(f"ZIP contiene ruta insegura: {member.filename}")
        archive.extractall(extraction_dir)

    return extraction_dir


def find_root_dir(extraction_dir: Path) -> Path:
    children = [path for path in extraction_dir.iterdir()]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return extraction_dir


def detect_multimedia_type(path: Path) -> str:
    extension = path.suffix.lower()
    if extension in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}:
        return "imagen"
    if extension in {".mp4", ".avi", ".mov", ".mkv"}:
        return "video"
    if extension in {".pdf", ".txt", ".doc", ".docx", ".md"}:
        return "documento"
    if extension in {".zip", ".rar", ".7z"}:
        return "comprimido"
    mime_type, _ = mimetypes.guess_type(path.name)
    return mime_type or "otro"


def infer_multimedia_label(file_path: Path) -> str | None:
    parent_name = normalize_text(file_path.parent.name)
    if parent_name in GENERIC_CASE_FOLDERS:
        return file_path.parent.name
    return None


def collect_text_sources(files: list[Path], logger: logging.Logger) -> tuple[list[str], int]:
    text_sources: list[str] = []
    errors = 0

    for file_path in files:
        extension = file_path.suffix.lower()
        if extension == ".txt":
            content, _encoding = safe_read_text(file_path)
            if content:
                text_sources.append(content)
            else:
                errors += 1
                logger.warning("No se pudo leer TXT: %s", file_path)
            continue

        if extension == ".docx":
            content = safe_read_docx_text(file_path)
            if content:
                text_sources.append(content)
            else:
                errors += 1
                logger.warning("DOCX sin texto extraible: %s", file_path)

    return text_sources, errors


def list_files(path: Path) -> list[Path]:
    return sorted([item for item in path.rglob("*") if item.is_file()], key=lambda item: str(item).lower())


def create_repair_from_files(
    connection,
    client_name: str,
    repair_name: str,
    files: list[Path],
    extraction_dir: Path,
    logger: logging.Logger,
    stats: ImportStats,
) -> None:
    if not files:
        return

    client_id, created_client = upsert_client(connection, client_name)
    stats.clients += int(created_client)

    text_sources, errors = collect_text_sources(files, logger)
    stats.errors += errors

    relative_path = str(files[0].parent.relative_to(extraction_dir))
    file_names = [file_path.name for file_path in files]
    extracted = infer_repair_data(repair_name, relative_path, text_sources, file_names)

    equipment_id, created_equipment = upsert_equipo(
        connection,
        id_cliente=client_id,
        marca=extracted.marca,
        modelo_original=extracted.modelo_original,
        modelo_estandarizado=extracted.modelo_estandarizado,
        nro_serie=extracted.nro_serie,
    )
    stats.equipment += int(created_equipment)

    repair_id = create_reparacion(
        connection,
        id_equipo=equipment_id,
        fecha_ingreso=extracted.fecha_ingreso or today_iso(),
        falla_reportada=extracted.falla_reportada or extracted.resumen,
        diagnostico_tecnico=extracted.diagnostico_tecnico or extracted.resumen,
        estado=REPAIR_STATUS_RECEIVED,
    )
    stats.repairs += 1

    for file_path in files:
        add_multimedia(
            connection,
            id_reparacion=repair_id,
            ruta_archivo=str(file_path.relative_to(extraction_dir)),
            tipo_archivo=detect_multimedia_type(file_path),
            etiqueta=infer_multimedia_label(file_path),
        )
        stats.multimedia += 1


def import_client(
    connection,
    client_dir: Path,
    extraction_dir: Path,
    logger: logging.Logger,
    stats: ImportStats,
) -> None:
    child_dirs = sorted([path for path in client_dir.iterdir() if path.is_dir()], key=lambda item: item.name.lower())
    root_files = sorted([path for path in client_dir.iterdir() if path.is_file()], key=lambda item: item.name.lower())

    general_files = list(root_files)
    for child_dir in child_dirs:
        if normalize_text(child_dir.name) in GENERIC_CASE_FOLDERS:
            general_files.extend(list_files(child_dir))

    if general_files:
        create_repair_from_files(
            connection=connection,
            client_name=client_dir.name,
            repair_name=f"{client_dir.name} - general",
            files=sorted(general_files, key=lambda item: str(item).lower()),
            extraction_dir=extraction_dir,
            logger=logger,
            stats=stats,
        )

    for child_dir in child_dirs:
        if normalize_text(child_dir.name) in GENERIC_CASE_FOLDERS:
            continue
        files = list_files(child_dir)
        if not files:
            logger.info("Carpeta sin archivos: %s", child_dir)
            continue
        create_repair_from_files(
            connection=connection,
            client_name=client_dir.name,
            repair_name=child_dir.name,
            files=files,
            extraction_dir=extraction_dir,
            logger=logger,
            stats=stats,
        )


def main() -> int:
    args = parse_args()
    zip_path = Path(args.zip).expanduser().resolve()
    db_path = Path(args.db)
    workspace_dir = Path(args.workspace)
    logs_dir = Path(args.logs_dir)

    workspace_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    log_file = logs_dir / f"import_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logger = setup_logger(log_file)

    if not zip_path.exists():
        print(f"ZIP no encontrado: {zip_path}", file=sys.stderr)
        return 1

    extraction_dir = safe_extract_zip(zip_path, workspace_dir)
    connection = connect_sqlite(db_path)
    stats = ImportStats()

    try:
        root_dir = find_root_dir(extraction_dir)
        client_dirs = sorted([path for path in root_dir.iterdir() if path.is_dir()], key=lambda item: item.name.lower())

        for client_dir in client_dirs:
            try:
                import_client(connection, client_dir, extraction_dir, logger, stats)
            except Exception as exc:  # noqa: BLE001
                stats.errors += 1
                logger.exception("Error procesando cliente %s: %s", client_dir, exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Importacion fallida: %s", exc)
        connection.close()
        return 1

    print("")
    print("Reporte final de importacion")
    print(f"- Clientes creados: {stats.clients}")
    print(f"- Equipos creados: {stats.equipment}")
    print(f"- Reparaciones registradas: {stats.repairs}")
    print(f"- Archivos multimedia asociados: {stats.multimedia}")
    print(f"- Errores: {stats.errors}")
    print(f"- Base SQLite: {db_path.resolve()}")
    print(f"- Carpeta de extraccion: {extraction_dir.resolve()}")
    print(f"- Log: {log_file.resolve()}")

    connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
