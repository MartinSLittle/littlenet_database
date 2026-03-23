from __future__ import annotations

import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = PROJECT_ROOT / "src" / "import_jobs"
sys.path.insert(0, str(MODULE_ROOT))

from app_runtime import get_default_db_path
from repair_service import RepairFormData, create_repair_record
from repair_service import RepairSearchFilters, RepairUpdateData, load_repair_detail, search_repairs, update_repair_record
from schema import REPAIR_STATUS_RECEIVED, add_multimedia, connect_sqlite, create_reparacion, upsert_client, upsert_equipo


class SQLiteFlowTests(unittest.TestCase):
    def test_default_db_path_in_source_points_to_project_database(self) -> None:
        expected = PROJECT_ROOT / "littlenet_database.sqlite3"
        self.assertEqual(get_default_db_path(), expected)

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
                marca="Lenovo",
                modelo_original="Legion 5 15I",
                modelo_estandarizado="LEGION 5 15I",
                nro_serie="SERIE123456",
            )
            self.assertTrue(equipment_created)

            same_equipment_id, second_equipment_created = upsert_equipo(
                connection,
                id_cliente=client_id,
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

    def test_import_zip_creates_repair_centered_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            source_root = temp_root / "Trabajos"
            case_dir = source_root / "Cliente Uno" / "Notebook Acer Aspire 5"
            case_dir.mkdir(parents=True)
            (case_dir / "diagnostico.txt").write_text(
                "Falla reportada: No enciende\nDiagnostico tecnico: Falla en fuente\n",
                encoding="utf-8",
            )
            (case_dir / "foto.jpg").write_text("binary", encoding="utf-8")

            zip_path = temp_root / "trabajos.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                for file_path in source_root.rglob("*"):
                    archive.write(file_path, file_path.relative_to(source_root.parent))

            db_path = temp_root / "littlenet_database.sqlite3"
            workspace_dir = temp_root / "workspace"
            logs_dir = temp_root / "logs"

            subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "src" / "import_jobs" / "import_zip.py"),
                    "--zip",
                    str(zip_path),
                    "--db",
                    str(db_path),
                    "--workspace",
                    str(workspace_dir),
                    "--logs-dir",
                    str(logs_dir),
                ],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            connection = connect_sqlite(db_path)
            counts = {
                "clientes": connection.execute("SELECT COUNT(*) FROM clientes").fetchone()[0],
                "equipos": connection.execute("SELECT COUNT(*) FROM equipos").fetchone()[0],
                "reparaciones": connection.execute("SELECT COUNT(*) FROM reparaciones").fetchone()[0],
                "multimedia": connection.execute("SELECT COUNT(*) FROM multimedia").fetchone()[0],
            }
            self.assertEqual(counts, {"clientes": 1, "equipos": 1, "reparaciones": 1, "multimedia": 2})

            repair_row = connection.execute(
                """
                SELECT r.fecha_ingreso, r.falla_reportada, e.marca, e.modelo_original
                FROM reparaciones r
                JOIN equipos e ON e.id = r.id_equipo
                """
            ).fetchone()
            self.assertEqual(repair_row["marca"], "ACER")
            self.assertIn("Aspire", repair_row["modelo_original"])
            self.assertEqual(repair_row["fecha_ingreso"], date.today().isoformat())
            self.assertIn("No enciende", repair_row["falla_reportada"])

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
                SELECT c.nombre, c.celular, c.correo, e.marca, r.estado, r.costo, m.tipo_archivo
                FROM reparaciones r
                JOIN equipos e ON e.id = r.id_equipo
                JOIN clientes c ON c.id = e.id_cliente
                JOIN multimedia m ON m.id_reparacion = r.id
                """
            ).fetchone()
            self.assertEqual(row["nombre"], "Cliente Servicio")
            self.assertEqual(row["celular"], "11-5555-0000")
            self.assertEqual(row["correo"], "mail@test.local")
            self.assertEqual(row["marca"], "Dell")
            self.assertEqual(row["estado"], 1)
            self.assertEqual(row["costo"], 99.5)
            self.assertEqual(row["tipo_archivo"], "documento")
            connection.close()

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

            detail = load_repair_detail(db_path, created.repair_id)
            self.assertEqual(detail.cliente_nombre, "Ana Prueba")
            self.assertEqual(len(detail.multimedia), 1)

            updated = update_repair_record(
                db_path,
                RepairUpdateData(
                    client_id=detail.client_id,
                    equipment_id=detail.equipment_id,
                    repair_id=detail.repair_id,
                    cliente_nombre="Ana Prueba Editada",
                    cliente_celular="11-1000-9999",
                    cliente_correo="ana.editada@test.local",
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


if __name__ == "__main__":
    unittest.main()
