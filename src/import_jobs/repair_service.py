from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import sqlite3

from schema import (
    add_multimedia,
    connect_sqlite,
    create_reparacion,
    get_reparacion_full,
    get_tipo_equipo_id_by_name,
    list_clientes,
    list_multimedia_for_reparacion,
    list_tipos_equipo,
    search_reparaciones,
    update_client,
    update_equipo,
    update_reparacion,
    validate_tipo_equipo_id,
    upsert_client,
    upsert_equipo,
    validate_repair_status,
)


@dataclass
class RepairFormData:
    cliente_nombre: str
    cliente_celular: str | None = None
    cliente_correo: str | None = None
    equipo_tipo_id: int | None = None
    equipo_marca: str | None = None
    equipo_modelo_original: str | None = None
    equipo_modelo_estandarizado: str | None = None
    equipo_serie: str | None = None
    fecha_ingreso: str = ""
    fecha_egreso: str | None = None
    falla_reportada: str | None = None
    diagnostico_tecnico: str | None = None
    estado: int = 0
    costo: float | None = None
    archivos: list[Path] | None = None
    base_dir: Path | None = None


@dataclass
class RepairCreateResult:
    client_id: int
    client_created: bool
    equipment_id: int
    equipment_created: bool
    repair_id: int
    attached_files: int


@dataclass
class RepairSearchFilters:
    field: str | None = None
    value: str | None = None
    only_open: bool = False
    estado: int | None = None


@dataclass
class RepairSearchResult:
    repair_id: int
    cliente_nombre: str
    equipo_tipo_nombre: str | None
    equipo_marca: str | None
    equipo_modelo: str | None
    equipo_serie: str | None
    fecha_ingreso: str
    fecha_egreso: str | None
    estado: int
    costo: float | None


@dataclass
class ClientListItem:
    client_id: int
    nombre: str
    celular: str | None
    correo: str | None


@dataclass
class EquipmentTypeListItem:
    type_id: int
    nombre: str


@dataclass
class DbReferenceData:
    clients: list[ClientListItem]
    equipment_types: list[EquipmentTypeListItem]


@dataclass
class MultimediaItem:
    multimedia_id: int
    ruta_archivo: str
    tipo_archivo: str | None
    etiqueta: str | None


@dataclass
class RepairDetail:
    repair_id: int
    client_id: int
    equipment_id: int
    cliente_nombre: str
    cliente_celular: str | None
    cliente_correo: str | None
    equipo_tipo_id: int | None
    equipo_tipo_nombre: str | None
    equipo_marca: str | None
    equipo_modelo_original: str | None
    equipo_modelo_estandarizado: str | None
    equipo_serie: str | None
    fecha_ingreso: str
    fecha_egreso: str | None
    falla_reportada: str | None
    diagnostico_tecnico: str | None
    estado: int
    costo: float | None
    multimedia: list[MultimediaItem]


@dataclass
class RepairUpdateData:
    client_id: int
    equipment_id: int
    repair_id: int
    cliente_nombre: str
    cliente_celular: str | None = None
    cliente_correo: str | None = None
    equipo_tipo_id: int | None = None
    equipo_marca: str | None = None
    equipo_modelo_original: str | None = None
    equipo_modelo_estandarizado: str | None = None
    equipo_serie: str | None = None
    fecha_egreso: str | None = None
    falla_reportada: str | None = None
    diagnostico_tecnico: str | None = None
    estado: int = 0
    costo: float | None = None
    archivos: list[Path] | None = None
    base_dir: Path | None = None


@dataclass
class RepairUpdateResult:
    repair_id: int
    attached_files: int


def clean_optional_text(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def ensure_iso_date(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"El campo {field_name} es obligatorio.")
    try:
        return date.fromisoformat(cleaned).isoformat()
    except ValueError as exc:
        raise ValueError(f"El campo {field_name} debe usar formato YYYY-MM-DD.") from exc


def optional_iso_date(value: str | None, field_name: str) -> str | None:
    cleaned = clean_optional_text(value)
    if cleaned is None:
        return None
    return ensure_iso_date(cleaned, field_name)


def serialize_path(path: Path, base_dir: Path | None) -> str:
    resolved = path.expanduser().resolve()
    if base_dir is None:
        return str(resolved)
    try:
        return str(resolved.relative_to(base_dir.expanduser().resolve()))
    except ValueError:
        return str(resolved)


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
    return "otro"


def validate_repair_form(data: RepairFormData) -> RepairFormData:
    cliente_nombre = clean_optional_text(data.cliente_nombre)
    if not cliente_nombre:
        raise ValueError("El nombre del cliente es obligatorio.")

    fecha_ingreso = ensure_iso_date(data.fecha_ingreso, "fecha_ingreso")
    fecha_egreso = optional_iso_date(data.fecha_egreso, "fecha_egreso")

    validate_repair_status(data.estado)

    if data.costo is not None and data.costo < 0:
        raise ValueError("El costo no puede ser negativo.")
    if data.equipo_tipo_id is None:
        raise ValueError("El tipo de equipo es obligatorio.")

    archivos = [Path(path).expanduser() for path in (data.archivos or [])]
    for path in archivos:
        if not path.exists() or not path.is_file():
            raise ValueError(f"Archivo multimedia no encontrado: {path}")

    return RepairFormData(
        cliente_nombre=cliente_nombre,
        cliente_celular=clean_optional_text(data.cliente_celular),
        cliente_correo=clean_optional_text(data.cliente_correo),
        equipo_tipo_id=data.equipo_tipo_id,
        equipo_marca=clean_optional_text(data.equipo_marca),
        equipo_modelo_original=clean_optional_text(data.equipo_modelo_original),
        equipo_modelo_estandarizado=clean_optional_text(data.equipo_modelo_estandarizado),
        equipo_serie=clean_optional_text(data.equipo_serie),
        fecha_ingreso=fecha_ingreso,
        fecha_egreso=fecha_egreso,
        falla_reportada=clean_optional_text(data.falla_reportada),
        diagnostico_tecnico=clean_optional_text(data.diagnostico_tecnico),
        estado=data.estado,
        costo=data.costo,
        archivos=archivos,
        base_dir=data.base_dir.expanduser().resolve() if data.base_dir else None,
    )


def validate_repair_update(data: RepairUpdateData) -> RepairUpdateData:
    cliente_nombre = clean_optional_text(data.cliente_nombre)
    if not cliente_nombre:
        raise ValueError("El nombre del cliente es obligatorio.")

    validate_repair_status(data.estado)

    if data.costo is not None and data.costo < 0:
        raise ValueError("El costo no puede ser negativo.")
    if data.equipo_tipo_id is None:
        raise ValueError("El tipo de equipo es obligatorio.")

    archivos = [Path(path).expanduser() for path in (data.archivos or [])]
    for path in archivos:
        if not path.exists() or not path.is_file():
            raise ValueError(f"Archivo multimedia no encontrado: {path}")

    return RepairUpdateData(
        client_id=data.client_id,
        equipment_id=data.equipment_id,
        repair_id=data.repair_id,
        cliente_nombre=cliente_nombre,
        cliente_celular=clean_optional_text(data.cliente_celular),
        cliente_correo=clean_optional_text(data.cliente_correo),
        equipo_tipo_id=data.equipo_tipo_id,
        equipo_marca=clean_optional_text(data.equipo_marca),
        equipo_modelo_original=clean_optional_text(data.equipo_modelo_original),
        equipo_modelo_estandarizado=clean_optional_text(data.equipo_modelo_estandarizado),
        equipo_serie=clean_optional_text(data.equipo_serie),
        fecha_egreso=optional_iso_date(data.fecha_egreso, "fecha_egreso"),
        falla_reportada=clean_optional_text(data.falla_reportada),
        diagnostico_tecnico=clean_optional_text(data.diagnostico_tecnico),
        estado=data.estado,
        costo=data.costo,
        archivos=archivos,
        base_dir=data.base_dir.expanduser().resolve() if data.base_dir else None,
    )


def create_repair_record(db_path: str | Path, data: RepairFormData) -> RepairCreateResult:
    validated = validate_repair_form(data)
    connection = connect_sqlite(db_path)
    try:
        validate_tipo_equipo_id(connection, validated.equipo_tipo_id)
        client_id, client_created = upsert_client(
            connection,
            validated.cliente_nombre,
            validated.cliente_celular,
            validated.cliente_correo,
        )
        equipment_id, equipment_created = upsert_equipo(
            connection,
            id_cliente=client_id,
            id_tipo_equipo=validated.equipo_tipo_id,
            marca=validated.equipo_marca,
            modelo_original=validated.equipo_modelo_original,
            modelo_estandarizado=validated.equipo_modelo_estandarizado,
            nro_serie=validated.equipo_serie,
        )
        repair_id = create_reparacion(
            connection,
            id_equipo=equipment_id,
            fecha_ingreso=validated.fecha_ingreso,
            fecha_egreso=validated.fecha_egreso,
            falla_reportada=validated.falla_reportada,
            diagnostico_tecnico=validated.diagnostico_tecnico,
            estado=validated.estado,
            costo=validated.costo,
        )

        attached_files = 0
        for file_path in validated.archivos or []:
            add_multimedia(
                connection,
                id_reparacion=repair_id,
                ruta_archivo=serialize_path(file_path, validated.base_dir),
                tipo_archivo=detect_multimedia_type(file_path),
                etiqueta=file_path.parent.name if file_path.parent != file_path else None,
            )
            attached_files += 1

        return RepairCreateResult(
            client_id=client_id,
            client_created=client_created,
            equipment_id=equipment_id,
            equipment_created=equipment_created,
            repair_id=repair_id,
            attached_files=attached_files,
        )
    except sqlite3.IntegrityError as exc:
        raise ValueError(
            "No se pudo guardar la reparacion. Revisa que el tipo exista y que el numero de serie no este duplicado."
        ) from exc
    finally:
        connection.close()


def search_repairs(db_path: str | Path, filters: RepairSearchFilters) -> list[RepairSearchResult]:
    connection = connect_sqlite(db_path)
    try:
        rows = search_reparaciones(
            connection,
            search_field=filters.field,
            search_value=filters.value,
            only_open=filters.only_open,
            estado=filters.estado,
        )
        return [
            RepairSearchResult(
                repair_id=int(row["reparacion_id"]),
                cliente_nombre=row["cliente_nombre"],
                equipo_tipo_nombre=row["equipo_tipo"],
                equipo_marca=row["equipo_marca"],
                equipo_modelo=row["equipo_modelo"],
                equipo_serie=row["equipo_serie"],
                fecha_ingreso=row["fecha_ingreso"],
                fecha_egreso=row["fecha_egreso"],
                estado=int(row["estado"]),
                costo=row["costo"],
            )
            for row in rows
        ]
    finally:
        connection.close()


def list_registered_clients(db_path: str | Path) -> list[ClientListItem]:
    connection = connect_sqlite(db_path)
    try:
        return [
            ClientListItem(
                client_id=int(row["id"]),
                nombre=row["nombre"],
                celular=row["celular"],
                correo=row["correo"],
            )
            for row in list_clientes(connection)
        ]
    finally:
        connection.close()


def list_equipment_types(db_path: str | Path) -> list[EquipmentTypeListItem]:
    connection = connect_sqlite(db_path)
    try:
        return [
            EquipmentTypeListItem(type_id=int(row["id"]), nombre=row["nombre"])
            for row in list_tipos_equipo(connection)
        ]
    finally:
        connection.close()


def load_db_reference_data(db_path: str | Path) -> DbReferenceData:
    connection = connect_sqlite(db_path)
    try:
        clients = [
            ClientListItem(
                client_id=int(row["id"]),
                nombre=row["nombre"],
                celular=row["celular"],
                correo=row["correo"],
            )
            for row in list_clientes(connection)
        ]
        equipment_types = [
            EquipmentTypeListItem(type_id=int(row["id"]), nombre=row["nombre"])
            for row in list_tipos_equipo(connection)
        ]
        return DbReferenceData(clients=clients, equipment_types=equipment_types)
    finally:
        connection.close()


def resolve_equipment_type_id(db_path: str | Path, nombre: str) -> int:
    connection = connect_sqlite(db_path)
    try:
        type_id = get_tipo_equipo_id_by_name(connection, nombre)
        if type_id is None:
            raise ValueError(f"Tipo de equipo no encontrado: {nombre}")
        return type_id
    finally:
        connection.close()


def load_repair_detail(db_path: str | Path, repair_id: int) -> RepairDetail:
    connection = connect_sqlite(db_path)
    try:
        row = get_reparacion_full(connection, repair_id)
        if row is None:
            raise ValueError(f"Reparacion no encontrada: {repair_id}")
        multimedia_rows = list_multimedia_for_reparacion(connection, repair_id)
        return RepairDetail(
            repair_id=int(row["reparacion_id"]),
            client_id=int(row["cliente_id"]),
            equipment_id=int(row["equipo_id"]),
            cliente_nombre=row["cliente_nombre"],
            cliente_celular=row["cliente_celular"],
            cliente_correo=row["cliente_correo"],
            equipo_tipo_id=row["id_tipo_equipo"],
            equipo_tipo_nombre=row["tipo_equipo_nombre"],
            equipo_marca=row["marca"],
            equipo_modelo_original=row["modelo_original"],
            equipo_modelo_estandarizado=row["modelo_estandarizado"],
            equipo_serie=row["nro_serie"],
            fecha_ingreso=row["fecha_ingreso"],
            fecha_egreso=row["fecha_egreso"],
            falla_reportada=row["falla_reportada"],
            diagnostico_tecnico=row["diagnostico_tecnico"],
            estado=int(row["estado"]),
            costo=row["costo"],
            multimedia=[
                MultimediaItem(
                    multimedia_id=int(item["id"]),
                    ruta_archivo=item["ruta_archivo"],
                    tipo_archivo=item["tipo_archivo"],
                    etiqueta=item["etiqueta"],
                )
                for item in multimedia_rows
            ],
        )
    finally:
        connection.close()


def update_repair_record(db_path: str | Path, data: RepairUpdateData) -> RepairUpdateResult:
    validated = validate_repair_update(data)
    connection = connect_sqlite(db_path)
    try:
        validate_tipo_equipo_id(connection, validated.equipo_tipo_id)
        update_client(
            connection,
            validated.client_id,
            validated.cliente_nombre,
            validated.cliente_celular,
            validated.cliente_correo,
        )
        update_equipo(
            connection,
            validated.equipment_id,
            validated.equipo_tipo_id,
            validated.equipo_marca,
            validated.equipo_modelo_original,
            validated.equipo_modelo_estandarizado,
            validated.equipo_serie,
        )
        update_reparacion(
            connection,
            validated.repair_id,
            validated.fecha_egreso,
            validated.falla_reportada,
            validated.diagnostico_tecnico,
            validated.estado,
            validated.costo,
        )

        attached_files = 0
        for file_path in validated.archivos or []:
            add_multimedia(
                connection,
                id_reparacion=validated.repair_id,
                ruta_archivo=serialize_path(file_path, validated.base_dir),
                tipo_archivo=detect_multimedia_type(file_path),
                etiqueta=file_path.parent.name if file_path.parent != file_path else None,
            )
            attached_files += 1

        return RepairUpdateResult(
            repair_id=validated.repair_id,
            attached_files=attached_files,
        )
    except sqlite3.IntegrityError as exc:
        raise ValueError("No se pudieron guardar los cambios. Revisa que el numero de serie no este duplicado.") from exc
    finally:
        connection.close()
