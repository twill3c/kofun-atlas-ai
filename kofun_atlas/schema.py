"""JSON Schema による出荷データ検証。"""

from __future__ import annotations

import json
import pathlib

from jsonschema import Draft202012Validator

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = PROJECT_ROOT / "schemas" / "kofun.schema.json"


def kofun_validator(schema_path: pathlib.Path | None = None) -> Draft202012Validator:
    path = schema_path or DEFAULT_SCHEMA
    schema = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    # スキーマ自体が壊れていたら、データを検査する前に落ちる。
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)
