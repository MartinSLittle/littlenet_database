from __future__ import annotations

import argparse
import sys
from pathlib import Path

from repair_service import RepairFormData, create_repair_record, list_equipment_types, resolve_equipment_type_id
from schema import REPAIR_STATUS_LABELS, validate_repair_status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Carga manual o semi-manual de cliente, equipo, reparacion y multimedia."
    )
    parser.add_argument("--db", default="littlenet_database.sqlite3", help="Ruta al archivo SQLite.")
    parser.add_argument("--cliente-nombre", required=True, help="Nombre del cliente.")
    parser.add_argument("--cliente-celular", help="Celular del cliente.")
    parser.add_argument("--cliente-correo", help="Correo del cliente.")
    parser.add_argument("--tipo-equipo", required=True, help="Nombre del tipo de equipo, por ejemplo Notebook.")
    parser.add_argument("--equipo-marca", help="Marca del equipo.")
    parser.add_argument("--equipo-modelo-original", help="Modelo tal como aparece en origen.")
    parser.add_argument("--equipo-modelo-estandarizado", help="Modelo normalizado para reutilizar busquedas.")
    parser.add_argument("--equipo-serie", help="Numero de serie del equipo.")
    parser.add_argument("--fecha-ingreso", required=True, help="Fecha ISO de ingreso. Ejemplo: 2026-03-15.")
    parser.add_argument("--fecha-egreso", help="Fecha ISO de egreso.")
    parser.add_argument("--falla-reportada", help="Descripcion de la falla reportada.")
    parser.add_argument("--diagnostico-tecnico", help="Diagnostico o trabajo realizado.")
    parser.add_argument("--estado", type=int, default=0, help="Estado numerico de la reparacion.")
    parser.add_argument("--costo", type=float, help="Costo de la reparacion.")
    parser.add_argument(
        "--archivo",
        action="append",
        default=[],
        help="Ruta a un archivo multimedia. Repetir el flag para asociar varios archivos.",
    )
    parser.add_argument(
        "--base-dir",
        help="Directorio base opcional para guardar rutas relativas de multimedia.",
    )
    return parser.parse_args()

def main() -> int:
    args = parse_args()

    try:
        validate_repair_status(args.estado)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        tipo_equipo_id = resolve_equipment_type_id(args.db, args.tipo_equipo)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        print("Tipos disponibles:", file=sys.stderr)
        for item in list_equipment_types(args.db):
            print(f"- {item.nombre}", file=sys.stderr)
        return 1

    try:
        result = create_repair_record(
            args.db,
            RepairFormData(
                cliente_nombre=args.cliente_nombre,
                cliente_celular=args.cliente_celular,
                cliente_correo=args.cliente_correo,
                equipo_tipo_id=tipo_equipo_id,
                equipo_marca=args.equipo_marca,
                equipo_modelo_original=args.equipo_modelo_original,
                equipo_modelo_estandarizado=args.equipo_modelo_estandarizado,
                equipo_serie=args.equipo_serie,
                fecha_ingreso=args.fecha_ingreso,
                fecha_egreso=args.fecha_egreso,
                falla_reportada=args.falla_reportada,
                diagnostico_tecnico=args.diagnostico_tecnico,
                estado=args.estado,
                costo=args.costo,
                archivos=[Path(raw_path) for raw_path in args.archivo],
                base_dir=Path(args.base_dir) if args.base_dir else None,
            ),
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print("Registro completado")
    print(f"- Cliente: {result.client_id} ({'creado' if result.client_created else 'reutilizado'})")
    print(f"- Equipo: {result.equipment_id} ({'creado' if result.equipment_created else 'reutilizado'})")
    print(f"- Reparacion: {result.repair_id}")
    print(f"- Multimedia asociada: {result.attached_files}")
    print("- Estados permitidos:")
    for key, label in REPAIR_STATUS_LABELS.items():
        print(f"  {key} = {label}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
