from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from sqlalchemy.orm import Session

from models import ChatQaCase

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _load_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for si in root.findall(f"{NS}si"):
        text_node = si.find(f"{NS}t")
        if text_node is not None and text_node.text is not None:
            strings.append(text_node.text)
            continue
        parts = [node.text or "" for node in si.iter(f"{NS}t")]
        strings.append("".join(parts))
    return strings


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.get("t")
    value_node = cell.find(f"{NS}v")
    if value_node is None or value_node.text is None:
        return ""
    raw = value_node.text
    if cell_type == "s":
        return shared_strings[int(raw)]
    return raw


def _parse_u_time(raw: str) -> float:
    try:
        return float(raw.strip())
    except (TypeError, ValueError):
        return 0.0


def parse_chat_qa_xlsx(path: Path) -> list[dict[str, str | float]]:
    if not path.is_file():
        return []

    rows: list[dict[str, str | float]] = []
    with zipfile.ZipFile(path) as zf:
        shared_strings = _load_shared_strings(zf)
        sheet = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
        sheet_rows = sheet.findall(f"{NS}sheetData/{NS}row")
        for index, row in enumerate(sheet_rows):
            if index == 0:
                continue
            cells = [_cell_value(cell, shared_strings) for cell in row.findall(f"{NS}c")]
            if len(cells) < 10:
                continue
            status = cells[9].strip()
            if status and status != "正常":
                continue
            rows.append(
                {
                    "user_id": cells[0].strip(),
                    "app_name": cells[1].strip(),
                    "role_id": cells[2].strip(),
                    "role_name": cells[3].strip(),
                    "question": cells[5].strip(),
                    "answer": cells[6].strip(),
                    "status": status or "正常",
                    "u_time": _parse_u_time(cells[8]),
                }
            )
    return rows


def upsert_chat_qa_rows(db: Session, parsed_rows: list[dict[str, str | float]]) -> int:
    inserted = 0
    for row in parsed_rows:
        if not row["user_id"] or not row["role_id"]:
            continue
        existing = (
            db.query(ChatQaCase)
            .filter(
                ChatQaCase.user_id == row["user_id"],
                ChatQaCase.role_id == row["role_id"],
                ChatQaCase.app_name == row["app_name"],
                ChatQaCase.question == row["question"],
                ChatQaCase.answer == row["answer"],
            )
            .first()
        )
        if existing:
            u_time = float(row["u_time"])
            if existing.u_time != u_time:
                existing.u_time = u_time
            continue
        db.add(ChatQaCase(**row))
        inserted += 1
    db.commit()
    return inserted


def import_chat_qa_from_xlsx(db: Session, xlsx_path: Path) -> int:
    return upsert_chat_qa_rows(db, parse_chat_qa_xlsx(xlsx_path))


def import_chat_qa_from_dir(db: Session, directory: Path) -> int:
    if not directory.is_dir():
        return 0
    total = 0
    for path in sorted(directory.glob("*.xlsx")):
        total += import_chat_qa_from_xlsx(db, path)
    return total


def ensure_chat_qa_cases(db: Session, seed_dir: Path | None = None) -> int:
    if db.query(ChatQaCase.id).first():
        return 0
    if seed_dir is None or not seed_dir.is_dir():
        return 0
    return import_chat_qa_from_dir(db, seed_dir)
