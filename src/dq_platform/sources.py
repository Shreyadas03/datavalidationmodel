"""Unified Excel and SQL source-loading helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import pandas as pd

from dq_platform.connection import (
    SqlServerConnectionSettings,
    list_table_names,
    load_table_dataframe,
    read_table_columns,
)
from dq_platform.io_utils import load_dataframe, read_header_columns, resolve_path

SourceMode = Literal["excel", "sql"]


@dataclass(frozen=True)
class SourceSpec:
    mode: SourceMode
    path: Optional[str] = None
    sheet_name: Optional[str] = None
    table_name: Optional[str] = None
    connection_settings: Optional[SqlServerConnectionSettings] = None


def list_sql_tables(
    connection_settings: Optional[SqlServerConnectionSettings] = None,
) -> list[str]:
    if connection_settings is not None:
        return list_table_names(connection_settings)
    return list_table_names()


def read_source_columns(source: SourceSpec) -> list[str]:
    if source.mode == "excel":
        return read_header_columns(source.path or "", source.sheet_name)
    if source.mode == "sql":
        if source.connection_settings is not None:
            return read_table_columns(source.table_name or "", source.connection_settings)
        return read_table_columns(source.table_name or "")
    raise ValueError(f"Unsupported source mode: {source.mode}")


def load_source_dataframe(source: SourceSpec) -> pd.DataFrame:
    if source.mode == "excel":
        return load_dataframe(source.path or "", source.sheet_name)
    if source.mode == "sql":
        if source.connection_settings is not None:
            return load_table_dataframe(source.table_name or "", source.connection_settings)
        return load_table_dataframe(source.table_name or "")
    raise ValueError(f"Unsupported source mode: {source.mode}")


def describe_source(source: SourceSpec) -> str:
    if source.mode == "excel":
        path = resolve_path(source.path or "")
        sheet = str(source.sheet_name or "").strip() or "<first sheet>"
        return f"{path} ({sheet})"
    if source.mode == "sql":
        table_name = str(source.table_name or "").strip()
        if not table_name:
            raise ValueError("No SQL table selected.")
        if source.connection_settings is not None:
            settings = source.connection_settings
            return f"SQL Server table {table_name} ({settings.server}/{settings.database})"
        return f"SQL Server table {table_name}"
    raise ValueError(f"Unsupported source mode: {source.mode}")
