from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = PROJECT_ROOT / "src" / "import_jobs"
sys.path.insert(0, str(MODULE_ROOT))

import app_runtime
from app_runtime import get_default_db_path
from repair_service import RepairFormData, create_repair_record, list_equipment_types, list_registered_clients
from repair_service import RepairSearchFilters, RepairUpdateData, load_repair_detail, search_repairs, update_repair_record
from repair_service import load_db_reference_data
from schema import (
    REPAIR_STATUS_RECEIVED,
    add_multimedia,
    connect_sqlite,
    create_reparacion,
    get_tipo_equipo_id_by_name,
    upsert_client,
    upsert_equipo,
)


class SQLiteFlowTests(unittest.TestCase):
    def get_type_id(self, connection, nombre: str = "Notebook") -> int:
        type_id = get_tipo_equipo_id_by_name(connection, nombre)
        self.assertIsNotNone(type_id)
        return int(type_id)

    def test_default_db_path_in_source_points_to_project_database(self) -> None:
        expected = PROJECT_ROOT / "littlenet_database.sqlite3"
        self.assertEqual(get_default_db_path(), expected)

    def test_last_db_path_config_roundtrip_and_missing_path_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            config_path = temp_root / "gui_config.json"
            saved_db = temp_root / "custom.sqlite3"
            saved_db.write_text("", encoding="utf-8")
            default_db = temp_root / "default.sqlite3"

            with patch.object(app_runtime, "get_config_path", return_value=config_path), patch.object(
                app_runtime, "get_default_db_path", return_value=default_db
            ):
                app_runtime.save_last_db_path(saved_db)
                loaded_path, warning = app_runtime.load_last_db_path()
                self.assertEqual(loaded_path, saved_db)
                self.assertIsNone(warning)

                saved_db.unlink()
                fallback_path, fallback_warning = app_runtime.load_last_db_path()
                self.assertEqual(fallback_path, default_db)
                self.assertIsNotNone(fallback_warning)

    def test_manual_flow_reuses_entities_and_enforces_foreign_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            db_path = temp_root / "littlenet_database.sqlite3"
            media_path = temp_root / "foto.jpg"
            media_path.write_text("image-bytes", encoding="utf-8")

            connection = connect_sqlite(db_path)

            client_id, client_created = upsert_client(connection, "Cliente Demo", "11-1234", "demo@test.local")
            self.assertTrue(client_created)

            same_client_id, second_client_created = upsert_client(connection, "  cliente   demo ", None)
            self.assertFalse(second_client_created)
            self.assertEqual(client_id, same_client_id)
            client_row = connection.execute(
                "SELECT nombre, celular, correo FROM clientes WHERE id = ?",
                (client_id,),
            ).fetchone()
            self.assertEqual(client_row["nombre"], "Cliente Demo")
            self.assertEqual(client_row["celular"], "11-1234")
            self.assertEqual(client_row["correo"], "demo@test.local")

            equipment_id, equipment_created = upsert_equipo(
                connection,
                id_cliente=client_id,
                id_tipo_equipo=self.get_type_id(connection),
                marca="Lenovo",
                modelo_original="Legion 5 15I",
                modelo_estandarizado="LEGION 5 15I",
                nro_serie="SERIE123456",
            )
            self.assertTrue(equipment_created)

            same_equipment_id, second_equipment_created = upsert_equipo(
                connection,
                id_cliente=client_id,
                id_tipo_equipo=self.get_type_id(connection),
                marca="lenovo",
                modelo_original="Legion 5 15I",
                modelo_estandarizado="LEGION 5 15I",
                nro_serie="SERIE123456",
            )
            self.assertFalse(second_equipment_created)
            self.assertEqual(equipment_id, same_equipment_id)

            repair_id = create_reparacion(
                connection,
                id_equipo=equipment_id,
                fecha_ingreso="2026-03-15",
                falla_reportada="No enciende",
                diagnostico_tecnico="Se cambia fuente",
                estado=REPAIR_STATUS_RECEIVED,
                costo=150.0,
            )

            add_multimedia(connection, repair_id, str(media_path), "imagen", "Fotos")

            counts = {
                "clientes": connection.execute("SELECT COUNT(*) FROM clientes").fetchone()[0],
                "equipos": connection.execute("SELECT COUNT(*) FROM equipos").fetchone()[0],
                "reparaciones": connection.execute("SELECT COUNT(*) FROM reparaciones").fetchone()[0],
                "multimedia": connection.execute("SELECT COUNT(*) FROM multimedia").fetchone()[0],
            }
            self.assertEqual(counts, {"clientes": 1, "equipos": 1, "reparaciones": 1, "multimedia": 1})

            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO multimedia (id_reparacion, ruta_archivo) VALUES (?, ?)",
                    (9999, "fantasma.jpg"),
                )

            connection.close()

    def test_shared_service_creates_record_for_cli_and_gui(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            db_path = temp_root / "service.sqlite3"
            media_path = temp_root / "informe.pdf"
            media_path.write_text("contenido", encoding="utf-8")

            result = create_repair_record(
                db_path,
                RepairFormData(
                    cliente_nombre="Cliente Servicio",
                    cliente_celular="11-5555-0000",
                    cliente_correo="mail@test.local",
                    equipo_tipo_id=list_equipment_types(db_path)[0].type_id,
                    equipo_marca="Dell",
                    equipo_modelo_original="Inspiron 15",
                    equipo_modelo_estandarizado="INSPIRON 15",
                    equipo_serie="SRV0001",
                    fecha_ingreso="2026-03-15",
                    falla_reportada="No carga",
                    diagnostico_tecnico="Se cambia conector",
                    estado=1,
                    costo=99.5,
                    archivos=[media_path],
                ),
            )

            self.assertEqual(result.attached_files, 1)

            connection = connect_sqlite(db_path)
            row = connection.execute(
                """
                SELECT c.nombre, c.celular, c.correo, te.nombre AS tipo_equipo, e.marca, r.estado, r.costo, m.tipo_archivo
                FROM reparaciones r
                JOIN equipos e ON e.id = r.id_equipo
                JOIN tipos_equipo te ON te.id = e.id_tipo_equipo
                JOIN clientes c ON c.id = e.id_cliente
                JOIN multimedia m ON m.id_reparacion = r.id
                """
            ).fetchone()
            self.assertEqual(row["nombre"], "Cliente Servicio")
            self.assertEqual(row["celular"], "11-5555-0000")
            self.assertEqual(row["correo"], "mail@test.local")
            self.assertEqual(row["tipo_equipo"], "Notebook")
            self.assertEqual(row["marca"], "Dell")
            self.assertEqual(row["estado"], 1)
            self.assertEqual(row["costo"], 99.5)
            self.assertEqual(row["tipo_archivo"], "documento")
            connection.close()

    def test_list_registered_clients_returns_saved_contact_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            db_path = temp_root / "clients.sqlite3"
            connection = connect_sqlite(db_path)
            upsert_client(connection, "Cliente Zeta", "11-9999", "zeta@test.local")
            upsert_client(connection, "Cliente Alfa", None, "alfa@test.local")
            connection.close()

            clients = list_registered_clients(db_path)

            self.assertEqual([client.nombre for client in clients], ["Cliente Alfa", "Cliente Zeta"])
            self.assertEqual(clients[0].correo, "alfa@test.local")
            self.assertEqual(clients[1].celular, "11-9999")

    def test_load_db_reference_data_uses_single_connection_for_clients_and_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            db_path = temp_root / "reference.sqlite3"

            connection = connect_sqlite(db_path)
            upsert_client(connection, "Cliente Uno", "11-1111", "uno@test.local")
            connection.close()

            reference_data = load_db_reference_data(db_path)

            self.assertEqual([client.nombre for client in reference_data.clients], ["Cliente Uno"])
            self.assertEqual([item.nombre for item in reference_data.equipment_types], ["Notebook", "Mini-PC", "PC", "Otro"])

    def test_search_and_update_existing_repair_without_creating_new_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            db_path = temp_root / "editable.sqlite3"
            media_path = temp_root / "inicial.pdf"
            new_media_path = temp_root / "extra.jpg"
            media_path.write_text("contenido", encoding="utf-8")
            new_media_path.write_text("contenido-extra", encoding="utf-8")

            created = create_repair_record(
                db_path,
                RepairFormData(
                    cliente_nombre="Ana Prueba",
                    cliente_celular="11-1000-2000",
                    cliente_correo="ana@test.local",
                    equipo_tipo_id=list_equipment_types(db_path)[0].type_id,
                    equipo_marca="HP",
                    equipo_modelo_original="Pavilion 14",
                    equipo_serie="HP-EDIT-001",
                    fecha_ingreso="2026-03-15",
                    fecha_egreso="",
                    falla_reportada="No inicia",
                    diagnostico_tecnico="Pendiente",
                    estado=REPAIR_STATUS_RECEIVED,
                    costo=None,
                    archivos=[media_path],
                ),
            )

            open_results = search_repairs(
                db_path,
                RepairSearchFilters(field="cliente_nombre", value="Ana", only_open=True),
            )
            self.assertEqual(len(open_results), 1)
            self.assertEqual(open_results[0].repair_id, created.repair_id)
            self.assertIsNone(open_results[0].fecha_egreso)
            self.assertEqual(open_results[0].equipo_tipo_nombre, "Notebook")

            detail = load_repair_detail(db_path, created.repair_id)
            self.assertEqual(detail.cliente_nombre, "Ana Prueba")
            self.assertEqual(detail.equipo_tipo_nombre, "Notebook")
            self.assertEqual(len(detail.multimedia), 1)

            lookup_connection = connect_sqlite(db_path)
            pc_type_id = self.get_type_id(lookup_connection, "PC")
            lookup_connection.close()

            updated = update_repair_record(
                db_path,
                RepairUpdateData(
                    client_id=detail.client_id,
                    equipment_id=detail.equipment_id,
                    repair_id=detail.repair_id,
                    cliente_nombre="Ana Prueba Editada",
                    cliente_celular="11-1000-9999",
                    cliente_correo="ana.editada@test.local",
                    equipo_tipo_id=pc_type_id,
                    equipo_marca="HP",
                    equipo_modelo_original="Pavilion 14",
                    equipo_serie="HP-EDIT-001",
                    fecha_egreso="2026-03-20",
                    falla_reportada="No inicia, queda en logo",
                    diagnostico_tecnico="Se actualiza BIOS",
                    estado=1,
                    costo=250.0,
                    archivos=[new_media_path],
                ),
            )

            self.assertEqual(updated.repair_id, created.repair_id)
            self.assertEqual(updated.attached_files, 1)

            updated_detail = load_repair_detail(db_path, created.repair_id)
            self.assertEqual(updated_detail.cliente_nombre, "Ana Prueba Editada")
            self.assertEqual(updated_detail.cliente_celular, "11-1000-9999")
            self.assertEqual(updated_detail.equipo_tipo_nombre, "PC")
            self.assertEqual(updated_detail.fecha_egreso, "2026-03-20")
            self.assertEqual(updated_detail.estado, 1)
            self.assertEqual(updated_detail.costo, 250.0)
            self.assertEqual(len(updated_detail.multimedia), 2)

            connection = connect_sqlite(db_path)
            counts = {
                "clientes": connection.execute("SELECT COUNT(*) FROM clientes").fetchone()[0],
                "equipos": connection.execute("SELECT COUNT(*) FROM equipos").fetchone()[0],
                "reparaciones": connection.execute("SELECT COUNT(*) FROM reparaciones").fetchone()[0],
                "multimedia": connection.execute("SELECT COUNT(*) FROM multimedia").fetchone()[0],
            }
            self.assertEqual(counts, {"clientes": 1, "equipos": 1, "reparaciones": 1, "multimedia": 2})
            connection.close()

    def test_existing_database_migrates_contacto_to_celular_and_adds_correo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            db_path = temp_root / "legacy.sqlite3"
            legacy_connection = sqlite3.connect(db_path)
            legacy_connection.execute(
                """
                CREATE TABLE clientes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    contacto TEXT
                )
                """
            )
            legacy_connection.execute(
                "INSERT INTO clientes (nombre, contacto) VALUES (?, ?)",
                ("Cliente Legacy", "11-9999-1111"),
            )
            legacy_connection.commit()
            legacy_connection.close()

            connection = connect_sqlite(db_path)
            row = connection.execute(
                "SELECT nombre, contacto, celular, correo FROM clientes WHERE nombre = ?",
                ("Cliente Legacy",),
            ).fetchone()
            self.assertEqual(row["contacto"], "11-9999-1111")
            self.assertEqual(row["celular"], "11-9999-1111")
            self.assertIsNone(row["correo"])
            connection.close()

    def test_existing_equipment_rows_receive_default_type_and_seed_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            db_path = temp_root / "legacy_equipment.sqlite3"
            legacy_connection = sqlite3.connect(db_path)
            legacy_connection.execute("PRAGMA foreign_keys = ON")
            legacy_connection.executescript(
                """
                CREATE TABLE clientes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    celular TEXT,
                    correo TEXT
                );

                CREATE TABLE equipos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_cliente INTEGER NOT NULL,
                    marca TEXT,
                    modelo_original TEXT,
                    modelo_estandarizado TEXT,
                    nro_serie TEXT UNIQUE,
                    FOREIGN KEY (id_cliente) REFERENCES clientes(id)
                );
                """
            )
            legacy_connection.execute(
                "INSERT INTO clientes (nombre) VALUES (?)",
                ("Cliente Migrado",),
            )
            legacy_connection.execute(
                """
                INSERT INTO equipos (id_cliente, marca, modelo_original, modelo_estandarizado, nro_serie)
                VALUES (?, ?, ?, ?, ?)
                """,
                (1, "Lenovo", "ThinkPad", "THINKPAD", "LEG-001"),
            )
            legacy_connection.commit()
            legacy_connection.close()

            connection = connect_sqlite(db_path)
            tipos = connection.execute("SELECT id, nombre FROM tipos_equipo ORDER BY id").fetchall()
            self.assertEqual([row["nombre"] for row in tipos], ["Notebook", "Mini-PC", "PC", "Otro"])
            equipo = connection.execute(
                """
                SELECT e.id_tipo_equipo, te.nombre AS tipo_nombre
                FROM equipos e
                JOIN tipos_equipo te ON te.id = e.id_tipo_equipo
                WHERE e.nro_serie = ?
                """,
                ("LEG-001",),
            ).fetchone()
            self.assertEqual(equipo["id_tipo_equipo"], 1)
            self.assertEqual(equipo["tipo_nombre"], "Notebook")
            connection.close()


if __name__ == "__main__":
    unittest.main()
