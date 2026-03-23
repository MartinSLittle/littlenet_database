from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree


BRANDS = [
    "acer", "apple", "asus", "bangho", "dell", "exo", "gigabyte", "hp",
    "huawei", "ibm", "intel", "lenovo", "lg", "msi", "noblex", "pcbox",
    "samsung", "sony", "toshiba",
]

GENERIC_CASE_FOLDERS = {
    "adjuntos", "archivos", "documentacion", "documentos", "fotos",
    "imagenes", "imagenes", "media", "multimedia", "videos"
}

DATE_PATTERNS = [
    re.compile(r"\b(?P<y>\d{4})[-_/](?P<m>\d{1,2})[-_/](?P<d>\d{1,2})\b"),
    re.compile(r"\b(?P<d>\d{1,2})[-_/](?P<m>\d{1,2})[-_/](?P<y>\d{2,4})\b"),
]

FIELD_ALIASES = {
    "falla_reportada": ["falla reportada", "falla", "problema", "motivo", "detalle de falla"],
    "diagnostico_tecnico": [
        "diagnostico", "diagnostico tecnico", "diagnostico final",
        "diagnostico técnico", "resultado", "conclusion tecnica", "conclusion técnica",
        "trabajo realizado", "reparacion realizada", "reparacion realizada"
    ],
    "nro_serie": ["nro serie", "numero de serie", "número de serie", "serie", "serial", "s/n"],
    "observaciones": ["observaciones", "notas", "nota", "comentarios", "detalle"],
}


@dataclass
class ParsedDate:
    raw: str
    iso: str


@dataclass
class ExtractedRepairData:
    marca: str | None = None
    modelo_original: str | None = None
    modelo_estandarizado: str | None = None
    nro_serie: str | None = None
    fecha_ingreso: str | None = None
    falla_reportada: str | None = None
    diagnostico_tecnico: str | None = None
    resumen: str | None = None


def normalize_text(value: str) -> str:
    return " ".join(value.lower().strip().split())


def clean_sentence(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "")
    return value.strip(" -_:;\t\r\n")


def safe_read_text(path: Path) -> tuple[str | None, str | None]:
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=encoding), encoding
        except UnicodeDecodeError:
            continue
        except OSError:
            return None, None
    return None, None


def safe_read_docx_text(path: Path) -> str | None:
    try:
        with zipfile.ZipFile(path) as archive:
            raw_xml = archive.read("word/document.xml")
    except (KeyError, OSError, zipfile.BadZipFile):
        return None

    try:
        tree = ElementTree.fromstring(raw_xml)
    except ElementTree.ParseError:
        return None

    texts: list[str] = []
    for node in tree.iter():
        if node.tag.endswith("}t") and node.text:
            texts.append(node.text)
    content = " ".join(texts).strip()
    return content or None


def detect_brand(texts: Iterable[str]) -> str | None:
    blob = normalize_text(" ".join(texts))
    for brand in BRANDS:
        if re.search(rf"\b{re.escape(brand)}\b", blob):
            return brand.upper()
    return None


def detect_model(texts: Iterable[str], brand: str | None) -> str | None:
    source = " ".join(texts)
    if brand:
        pattern = re.compile(
            rf"\b{re.escape(brand)}\b[\s\-_:]+([A-Za-z0-9][A-Za-z0-9\-/\. ]{{2,60}})",
            re.IGNORECASE,
        )
        match = pattern.search(source)
        if match:
            candidate = clean_sentence(match.group(1))
            candidate = re.split(
                r"\b(?:presupuesto|diagnostico|diagnostico|nota|del|fecha|falla|problema)\b",
                candidate,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0].strip()
            if candidate:
                return candidate[:120]

    generic = re.search(r"\b([A-Z]{1,4}\d{2,5}[A-Z0-9\-]{0,20})\b", source)
    if generic:
        return generic.group(1)
    return None


def standardize_model(value: str | None) -> str | None:
    cleaned = clean_sentence(value or "")
    if not cleaned:
        return None
    return " ".join(cleaned.upper().split())


def extract_date(texts: Iterable[str]) -> ParsedDate | None:
    blob = " ".join(texts)
    for pattern in DATE_PATTERNS:
        match = pattern.search(blob)
        if not match:
            continue

        year = int(match.group("y"))
        month = int(match.group("m"))
        day = int(match.group("d"))
        if year < 100:
            year += 2000

        try:
            parsed = datetime(year, month, day)
        except ValueError:
            continue
        return ParsedDate(raw=match.group(0), iso=parsed.date().isoformat())
    return None


def extract_labeled_fields(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for line in lines:
        normalized_line = normalize_text(line)
        for field_name, aliases in FIELD_ALIASES.items():
            for alias in aliases:
                if not normalized_line.startswith(alias):
                    continue
                _, _, value = line.partition(":")
                if not value.strip():
                    parts = re.split(r"\s+-\s+|\s{2,}", line, maxsplit=1)
                    value = parts[1] if len(parts) > 1 else ""
                value = clean_sentence(value)
                if value:
                    result[field_name] = value
                break
    return result


def detect_serial(texts: Iterable[str]) -> str | None:
    serial_pattern = re.compile(
        r"(?:serial|serie|numero de serie|nro serie|s/n)\s*[:#-]?\s*([A-Za-z0-9\-]{6,40})",
        re.IGNORECASE,
    )
    for text in texts:
        match = serial_pattern.search(text)
        if match:
            return clean_sentence(match.group(1))
    return None


def summarize_text_blob(text: str, limit: int = 240) -> str | None:
    cleaned = clean_sentence(text.replace("\n", " "))
    if not cleaned:
        return None
    return cleaned[:limit]


def infer_repair_data(
    repair_name: str,
    relative_path: str,
    text_sources: list[str],
    file_names: list[str],
) -> ExtractedRepairData:
    hints = [repair_name, relative_path, *file_names, *text_sources]
    brand = detect_brand(hints)
    model_original = detect_model(hints, brand)
    parsed_date = extract_date(hints)

    combined_fields: dict[str, str] = {}
    for text in text_sources:
        combined_fields.update(extract_labeled_fields(text))

    fallback_summary = summarize_text_blob(text_sources[0]) if text_sources else None

    return ExtractedRepairData(
        marca=brand,
        modelo_original=model_original,
        modelo_estandarizado=standardize_model(model_original),
        nro_serie=combined_fields.get("nro_serie") or detect_serial(hints),
        fecha_ingreso=parsed_date.iso if parsed_date else None,
        falla_reportada=combined_fields.get("falla_reportada") or fallback_summary,
        diagnostico_tecnico=combined_fields.get("diagnostico_tecnico") or combined_fields.get("observaciones"),
        resumen=combined_fields.get("observaciones") or fallback_summary,
    )
