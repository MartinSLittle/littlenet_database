from __future__ import annotations

import sqlite3
from pathlib import Path


REPAIR_STATUS_RECEIVED = 0
REPAIR_STATUS_IN_PROGRESS = 1
REPAIR_STATUS_WAITING_PARTS = 2
REPAIR_STATUS_READY = 3
REPAIR_STATUS_DELIVERED = 4

# Estado numerico documentado para usar el mismo criterio en toda la app.
REPAIR_STATUS_LABELS = {
    REPAIR_STATUS_RECEIVED: "ingresado",
    REPAIR_STATUS_IN_PROGRESS: "en_proceso",
    REPAIR_STATUS_WAITING_PARTS: "esperando_repuestos",
    REPAIR_STATUS_READY: "listo_para_entrega",
    REPAIR_STATUS_DELIVERED: "entregado",
}

DEFAULT_EQUIPMENT_TYPES = (
    "Notebook",
    "Mini-PC",
    "PC",
    "Otro",
)


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    celular TEXT,
    correo TEXT
);

CREATE TABLE IF NOT EXISTS tipos_equipo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS equipos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_cliente INTEGER NOT NULL,
    id_tipo_equipo INTEGER,
    marca TEXT,
    modelo_original TEXT,
    modelo_estandarizado TEXT,
    nro_serie TEXT UNIQUE,
    FOREIGN KEY (id_cliente) REFERENCES clientes(id),
    FOREIGN KEY (id_tipo_equipo) REFERENCES tipos_equipo(id)
);

CREATE TABLE IF NOT EXISTS reparaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_equipo INTEGER NOT NULL,
    fecha_ingreso TEXT NOT NULL,
    fecha_egreso TEXT,
    falla_reportada TEXT,
    diagnostico_tecnico TEXT,
    estado INTEGER NOT NULL DEFAULT 0,
    costo REAL,
    FOREIGN KEY (id_equipo) REFERENCES equipos(id)
);

CREATE TABLE IF NOT EXISTS multimedia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_reparacion INTEGER NOT NULL,
    ruta_archivo TEXT NOT NULL,
    tipo_archivo TEXT,
    etiqueta TEXT,
    FOREIGN KEY (id_reparacion) REFERENCES reparaciones(id)
);

CREATE INDEX IF NOT EXISTS idx_equipos_cliente ON equipos(id_cliente);
CREATE INDEX IF NOT EXISTS idx_reparaciones_equipo ON reparaciones(id_equipo);
CREATE INDEX IF NOT EXISTS idx_multimedia_reparacion ON multimedia(id_reparacion);
"""


def normalize_lookup(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def create_equipos_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE equipos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_cliente INTEGER NOT NULL,
            id_tipo_equipo INTEGER,
            marca TEXT,
            modelo_original TEXT,
            modelo_estandarizado TEXT,
            nro_serie TEXT UNIQUE,
            FOREIGN KEY (id_cliente) REFERENCES clientes(id),
            FOREIGN KEY (id_tipo_equipo) REFERENCES tipos_equipo(id)
        )
        """
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_equipos_cliente ON equipos(id_cliente)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_equipos_tipo ON equipos(id_tipo_equipo)")


def seed_default_equipment_types(connection: sqlite3.Connection) -> None:
    total = connection.execute("SELECT COUNT(*) FROM tipos_equipo").fetchone()[0]
    if total:
        return
    connection.executemany(
        "INSERT INTO tipos_equipo (nombre) VALUES (?)",
        [(name,) for name in DEFAULT_EQUIPMENT_TYPES],
    )


def get_tipo_equipo_id_by_name(connection: sqlite3.Connection, nombre: str) -> int | None:
    row = connection.execute(
        "SELECT id FROM tipos_equipo WHERE LOWER(nombre) = LOWER(?)",
        (nombre.strip(),),
    ).fetchone()
    if row is None:
        return None
    return int(row["id"])


def get_default_tipo_equipo_id(connection: sqlite3.Connection) -> int:
    default_id = get_tipo_equipo_id_by_name(connection, DEFAULT_EQUIPMENT_TYPES[0])
    if default_id is None:
        raise ValueError("No se encontro el tipo de equipo por defecto.")
    return default_id


def validate_tipo_equipo_id(connection: sqlite3.Connection, id_tipo_equipo: int) -> None:
    row = connection.execute(
        "SELECT 1 FROM tipos_equipo WHERE id = ?",
        (id_tipo_equipo,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Tipo de equipo inexistente: {id_tipo_equipo}")


def list_tipos_equipo(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT id, nombre
        FROM tipos_equipo
        ORDER BY id
        """
    ).fetchall()


def equipos_has_type_foreign_key(connection: sqlite3.Connection) -> bool:
    foreign_keys = connection.execute("PRAGMA foreign_key_list(equipos)").fetchall()
    return any(
        row["table"] == "tipos_equipo" and row["from"] == "id_tipo_equipo"
        for row in foreign_keys
    )


def migrate_equipos_table(connection: sqlite3.Connection, default_type_id: int, has_type_column: bool) -> None:
    connection.execute("ALTER TABLE equipos RENAME TO equipos_legacy")
    create_equipos_table(connection)
    source_type_column = "id_tipo_equipo" if has_type_column else str(default_type_id)
    connection.execute(
        f"""
        INSERT INTO equipos (
            id, id_cliente, id_tipo_equipo, marca, modelo_original, modelo_estandarizado, nro_serie
        )
        SELECT
            id,
            id_cliente,
            COALESCE({source_type_column}, {default_type_id}),
            marca,
            modelo_original,
            modelo_estandarizado,
            nro_serie
        FROM equipos_legacy
        """
    )
    connection.execute("DROP TABLE equipos_legacy")


def ensure_equipment_type_schema(connection: sqlite3.Connection) -> None:
    equipment_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(equipos)").fetchall()
    }
    default_type_id = get_default_tipo_equipo_id(connection)
    has_type_column = "id_tipo_equipo" in equipment_columns

    if not has_type_column or not equipos_has_type_foreign_key(connection):
        connection.execute("PRAGMA foreign_keys = OFF")
        try:
            migrate_equipos_table(connection, default_type_id, has_type_column)
        finally:
            connection.execute("PRAGMA foreign_keys = ON")

    connection.execute(
        """
        UPDATE equipos
        SET id_tipo_equipo = ?
        WHERE id_tipo_equipo IS NULL
        """,
        (default_type_id,),
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_equipos_cliente ON equipos(id_cliente)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_equipos_tipo ON equipos(id_tipo_equipo)")


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA_SQL)
    client_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(clientes)").fetchall()
    }
    if "celular" not in client_columns:
        connection.execute("ALTER TABLE clientes ADD COLUMN celular TEXT")
    if "correo" not in client_columns:
        connection.execute("ALTER TABLE clientes ADD COLUMN correo TEXT")
    if "contacto" in client_columns:
        connection.execute(
            """
            UPDATE clientes
            SET celular = COALESCE(celular, contacto)
            WHERE contacto IS NOT NULL AND TRIM(contacto) != ''
            """
        )
    seed_default_equipment_types(connection)
    ensure_equipment_type_schema(connection)
    connection.commit()


def connect_sqlite(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    ensure_schema(connection)
    return connection


def validate_repair_status(status: int) -> None:
    if status not in REPAIR_STATUS_LABELS:
        supported = ", ".join(f"{key}={value}" for key, value in REPAIR_STATUS_LABELS.items())
        raise ValueError(f"Estado de reparacion invalido: {status}. Estados permitidos: {supported}")


def upsert_client(
    connection: sqlite3.Connection,
    nombre: str,
    celular: str | None = None,
    correo: str | None = None,
) -> tuple[int, bool]:
    normalized_name = normalize_lookup(nombre)
    rows = connection.execute("SELECT id, nombre, celular, correo FROM clientes ORDER BY id").fetchall()

    for row in rows:
        if normalize_lookup(row["nombre"]) != normalized_name:
            continue
        if (celular and not row["celular"]) or (correo and not row["correo"]):
            connection.execute(
                "UPDATE clientes SET celular = COALESCE(celular, ?), correo = COALESCE(correo, ?) WHERE id = ?",
                (celular.strip() if celular else None, correo.strip() if correo else None, row["id"]),
            )
            connection.commit()
        return int(row["id"]), False

    cursor = connection.execute(
        "INSERT INTO clientes (nombre, celular, correo) VALUES (?, ?, ?)",
        (
            nombre.strip(),
            celular.strip() if celular else None,
            correo.strip() if correo else None,
        ),
    )
    connection.commit()
    return int(cursor.lastrowid), True


def upsert_equipo(
    connection: sqlite3.Connection,
    id_cliente: int,
    id_tipo_equipo: int,
    marca: str | None = None,
    modelo_original: str | None = None,
    modelo_estandarizado: str | None = None,
    nro_serie: str | None = None,
) -> tuple[int, bool]:
    validate_tipo_equipo_id(connection, id_tipo_equipo)
    clean_brand = marca.strip() if marca else None
    clean_original = modelo_original.strip() if modelo_original else None
    clean_standard = modelo_estandarizado.strip() if modelo_estandarizado else None
    clean_serial = nro_serie.strip() if nro_serie else None

    if clean_serial:
        row = connection.execute(
            "SELECT * FROM equipos WHERE nro_serie = ?",
            (clean_serial,),
        ).fetchone()
        if row is not None:
            connection.execute(
                """
                UPDATE equipos
                SET id_cliente = ?,
                    id_tipo_equipo = ?,
                    marca = COALESCE(marca, ?),
                    modelo_original = COALESCE(modelo_original, ?),
                    modelo_estandarizado = COALESCE(modelo_estandarizado, ?)
                WHERE id = ?
                """,
                (id_cliente, id_tipo_equipo, clean_brand, clean_original, clean_standard, row["id"]),
            )
            connection.commit()
            return int(row["id"]), False

    rows = connection.execute(
        """
        SELECT * FROM equipos
        WHERE id_cliente = ?
        ORDER BY id
        """,
        (id_cliente,),
    ).fetchall()
    desired_key = (
        normalize_lookup(clean_brand),
        normalize_lookup(clean_standard or clean_original),
    )

    for row in rows:
        row_key = (
            normalize_lookup(row["marca"]),
            normalize_lookup(row["modelo_estandarizado"] or row["modelo_original"]),
        )
        if desired_key == row_key and any(desired_key):
            connection.execute(
                """
                UPDATE equipos
                SET id_tipo_equipo = ?,
                    marca = COALESCE(marca, ?),
                    modelo_original = COALESCE(modelo_original, ?),
                    modelo_estandarizado = COALESCE(modelo_estandarizado, ?),
                    nro_serie = COALESCE(nro_serie, ?)
                WHERE id = ?
                """,
                (id_tipo_equipo, clean_brand, clean_original, clean_standard, clean_serial, row["id"]),
            )
            connection.commit()
            return int(row["id"]), False

    cursor = connection.execute(
        """
        INSERT INTO equipos (id_cliente, id_tipo_equipo, marca, modelo_original, modelo_estandarizado, nro_serie)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (id_cliente, id_tipo_equipo, clean_brand, clean_original, clean_standard, clean_serial),
    )
    connection.commit()
    return int(cursor.lastrowid), True


def create_reparacion(
    connection: sqlite3.Connection,
    id_equipo: int,
    fecha_ingreso: str,
    fecha_egreso: str | None = None,
    falla_reportada: str | None = None,
    diagnostico_tecnico: str | None = None,
    estado: int = REPAIR_STATUS_RECEIVED,
    costo: float | None = None,
) -> int:
    validate_repair_status(estado)
    cursor = connection.execute(
        """
        INSERT INTO reparaciones (
            id_equipo, fecha_ingreso, fecha_egreso, falla_reportada,
            diagnostico_tecnico, estado, costo
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (id_equipo, fecha_ingreso, fecha_egreso, falla_reportada, diagnostico_tecnico, estado, costo),
    )
    connection.commit()
    return int(cursor.lastrowid)


def update_client(
    connection: sqlite3.Connection,
    id_cliente: int,
    nombre: str,
    celular: str | None = None,
    correo: str | None = None,
) -> None:
    connection.execute(
        """
        UPDATE clientes
        SET nombre = ?, celular = ?, correo = ?
        WHERE id = ?
        """,
        (nombre, celular, correo, id_cliente),
    )
    connection.commit()


def list_clientes(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT id, nombre, celular, correo
        FROM clientes
        ORDER BY LOWER(nombre), id
        """
    ).fetchall()


def update_equipo(
    connection: sqlite3.Connection,
    id_equipo: int,
    id_tipo_equipo: int,
    marca: str | None = None,
    modelo_original: str | None = None,
    modelo_estandarizado: str | None = None,
    nro_serie: str | None = None,
) -> None:
    validate_tipo_equipo_id(connection, id_tipo_equipo)
    connection.execute(
        """
        UPDATE equipos
        SET id_tipo_equipo = ?, marca = ?, modelo_original = ?, modelo_estandarizado = ?, nro_serie = ?
        WHERE id = ?
        """,
        (id_tipo_equipo, marca, modelo_original, modelo_estandarizado, nro_serie, id_equipo),
    )
    connection.commit()


def update_reparacion(
    connection: sqlite3.Connection,
    id_reparacion: int,
    fecha_egreso: str | None = None,
    falla_reportada: str | None = None,
    diagnostico_tecnico: str | None = None,
    estado: int = REPAIR_STATUS_RECEIVED,
    costo: float | None = None,
) -> None:
    validate_repair_status(estado)
    connection.execute(
        """
        UPDATE reparaciones
        SET fecha_egreso = ?,
            falla_reportada = ?,
            diagnostico_tecnico = ?,
            estado = ?,
            costo = ?
        WHERE id = ?
        """,
        (fecha_egreso, falla_reportada, diagnostico_tecnico, estado, costo, id_reparacion),
    )
    connection.commit()


def search_reparaciones(
    connection: sqlite3.Connection,
    search_field: str | None = None,
    search_value: str | None = None,
    only_open: bool = False,
    estado: int | None = None,
) -> list[sqlite3.Row]:
    field_map = {
        "id_reparacion": "CAST(r.id AS TEXT)",
        "cliente_nombre": "c.nombre",
        "tipo_equipo": "te.nombre",
        "nro_serie": "e.nro_serie",
        "marca": "e.marca",
        "modelo": "COALESCE(e.modelo_estandarizado, e.modelo_original)",
    }
    if search_field not in field_map and search_field is not None:
        raise ValueError(f"Campo de busqueda invalido: {search_field}")

    conditions: list[str] = []
    params: list[object] = []

    cleaned_value = (search_value or "").strip()
    if cleaned_value and search_field:
        if search_field == "id_reparacion":
            conditions.append("CAST(r.id AS TEXT) = ?")
            params.append(cleaned_value)
        else:
            conditions.append(f"{field_map[search_field]} LIKE ?")
            params.append(f"%{cleaned_value}%")

    if only_open:
        conditions.append("(r.fecha_egreso IS NULL OR TRIM(r.fecha_egreso) = '')")

    if estado is not None:
        conditions.append("r.estado = ?")
        params.append(estado)

    where_sql = ""
    if conditions:
        where_sql = "WHERE " + " AND ".join(conditions)

    return connection.execute(
        f"""
        SELECT
            r.id AS reparacion_id,
            r.fecha_ingreso,
            r.fecha_egreso,
            r.estado,
            r.costo,
            c.nombre AS cliente_nombre,
            te.nombre AS equipo_tipo,
            e.marca AS equipo_marca,
            COALESCE(e.modelo_estandarizado, e.modelo_original) AS equipo_modelo,
            e.nro_serie AS equipo_serie
        FROM reparaciones r
        JOIN equipos e ON e.id = r.id_equipo
        LEFT JOIN tipos_equipo te ON te.id = e.id_tipo_equipo
        JOIN clientes c ON c.id = e.id_cliente
        {where_sql}
        ORDER BY r.id DESC
        """,
        params,
    ).fetchall()


def get_reparacion_full(connection: sqlite3.Connection, id_reparacion: int) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT
            r.id AS reparacion_id,
            r.fecha_ingreso,
            r.fecha_egreso,
            r.falla_reportada,
            r.diagnostico_tecnico,
            r.estado,
            r.costo,
            e.id AS equipo_id,
            e.id_tipo_equipo,
            te.nombre AS tipo_equipo_nombre,
            e.marca,
            e.modelo_original,
            e.modelo_estandarizado,
            e.nro_serie,
            c.id AS cliente_id,
            c.nombre AS cliente_nombre,
            c.celular AS cliente_celular,
            c.correo AS cliente_correo
        FROM reparaciones r
        JOIN equipos e ON e.id = r.id_equipo
        LEFT JOIN tipos_equipo te ON te.id = e.id_tipo_equipo
        JOIN clientes c ON c.id = e.id_cliente
        WHERE r.id = ?
        """,
        (id_reparacion,),
    ).fetchone()


def list_multimedia_for_reparacion(connection: sqlite3.Connection, id_reparacion: int) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT id, ruta_archivo, tipo_archivo, etiqueta
        FROM multimedia
        WHERE id_reparacion = ?
        ORDER BY id
        """,
        (id_reparacion,),
    ).fetchall()


def add_multimedia(
    connection: sqlite3.Connection,
    id_reparacion: int,
    ruta_archivo: str,
    tipo_archivo: str | None = None,
    etiqueta: str | None = None,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO multimedia (id_reparacion, ruta_archivo, tipo_archivo, etiqueta)
        VALUES (?, ?, ?, ?)
        """,
        (id_reparacion, ruta_archivo, tipo_archivo, etiqueta),
    )
    connection.commit()
    return int(cursor.lastrowid)
