"""SQL Server connection helpers for notebook SQL mode.

The initial non-secret defaults are seeded from ``notebooks/Test.ipynb``.
Credentials remain environment-driven so secrets do not live in source.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import pandas as pd
import pyodbc


@dataclass(frozen=True)
class SqlServerConnectionSettings:
    """Editable SQL Server connection settings used by the notebook UI."""

    driver: str = os.getenv("DQ_SQL_DRIVER", "ODBC Driver 18 for SQL Server")
    server: str = os.getenv("DQ_SQL_SERVER", "mart6.its.hpecorp.net")
    database: str = os.getenv("DQ_SQL_DATABASE", "TPM_winback")
    username: Optional[str] = os.getenv("DQ_SQL_USERNAME")
    password: Optional[str] = os.getenv("DQ_SQL_PASSWORD")
    authentication: Optional[str] = os.getenv("DQ_SQL_AUTHENTICATION")
    trusted_connection: bool = os.getenv("DQ_SQL_TRUSTED_CONNECTION", "true").lower() in {
        "1",
        "true",
        "yes",
    }
    encrypt: bool = os.getenv("DQ_SQL_ENCRYPT", "false").lower() in {"1", "true", "yes"}
    trust_server_certificate: bool = os.getenv(
        "DQ_SQL_TRUST_SERVER_CERTIFICATE", "true"
    ).lower() in {"1", "true", "yes"}
    connection_timeout_seconds: int = int(os.getenv("DQ_SQL_CONNECTION_TIMEOUT", "30"))

    def to_connection_string(self) -> str:
        parts = [
            f"DRIVER={{{self.driver}}}",
            f"SERVER={self.server}",
            f"DATABASE={self.database}",
            f"Encrypt={'yes' if self.encrypt else 'no'}",
            f"TrustServerCertificate={'yes' if self.trust_server_certificate else 'no'}",
            f"Connection Timeout={int(self.connection_timeout_seconds)}",
        ]
        if self.authentication and str(self.authentication).strip():
            parts.append(f"Authentication={str(self.authentication).strip()}")

        has_username = bool(self.username and str(self.username).strip())
        has_password = bool(self.password and str(self.password).strip())
        if has_username or has_password:
            if not (has_username and has_password):
                raise ValueError(
                    "SQL Server credentials are incomplete. Provide both "
                    "DQ_SQL_USERNAME and DQ_SQL_PASSWORD."
                )
            parts.extend([f"UID={str(self.username).strip()}", f"PWD={str(self.password).strip()}"])
        elif self.trusted_connection:
            parts.append("Trusted_Connection=yes")
        else:
            raise ValueError(
                "SQL Server credentials are incomplete. Provide username/password or "
                "enable trusted_connection in dq_platform/connection.py."
            )
        return ";".join(parts)


SQL_SERVER_SETTINGS = SqlServerConnectionSettings()


def get_connection(settings: SqlServerConnectionSettings = SQL_SERVER_SETTINGS) -> pyodbc.Connection:
    """Open a pyodbc connection using the configured SQL Server settings."""
    try:
        return pyodbc.connect(settings.to_connection_string())
    except pyodbc.Error as exc:
        error_text = str(exc)
        if "Cannot generate SSPI context" in error_text or "contact a domain controller" in error_text:
            raise ConnectionError(
                "SQL Server Windows authentication failed (SSPI/domain controller issue). "
                "If your machine is off-domain or cannot reach AD, set "
                "DQ_SQL_TRUSTED_CONNECTION=false and provide DQ_SQL_USERNAME/DQ_SQL_PASSWORD. "
                "If required by your server, also set DQ_SQL_AUTHENTICATION "
                "(for example: ActiveDirectoryPassword)."
            ) from exc
        raise


def _split_table_name(table_name: str) -> tuple[str, str]:
    cleaned = str(table_name).strip()
    if not cleaned:
        raise ValueError("No SQL table selected.")

    parts = [part.strip().strip("[]") for part in cleaned.split(".") if part.strip()]
    if len(parts) == 1:
        return "dbo", parts[0]
    if len(parts) == 2:
        return parts[0], parts[1]
    raise ValueError(
        f"Table name '{table_name}' must be 'table' or 'schema.table' for SQL Server."
    )


def _quote_identifier(name: str) -> str:
    return f"[{str(name).replace(']', ']]')}]"


def _qualified_table_name(table_name: str) -> str:
    schema_name, base_name = _split_table_name(table_name)
    return f"{_quote_identifier(schema_name)}.{_quote_identifier(base_name)}"


def list_table_names(
    settings: SqlServerConnectionSettings = SQL_SERVER_SETTINGS,
) -> list[str]:
    """List SQL Server base tables and views as schema-qualified names."""
    query = """
    SELECT TABLE_SCHEMA, TABLE_NAME
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_TYPE IN ('BASE TABLE', 'VIEW')
    ORDER BY TABLE_SCHEMA, TABLE_NAME
    """
    with get_connection(settings) as connection:
        frame = pd.read_sql(query, connection)
    return [f"{row.TABLE_SCHEMA}.{row.TABLE_NAME}" for row in frame.itertuples(index=False)]


def load_table_dataframe(
    table_name: str,
    settings: SqlServerConnectionSettings = SQL_SERVER_SETTINGS,
) -> pd.DataFrame:
    """Load a SQL Server table or view into a DataFrame."""
    query = f"SELECT * FROM {_qualified_table_name(table_name)}"
    with get_connection(settings) as connection:
        frame = pd.read_sql(query, connection)
    frame.columns = [str(column).strip() for column in frame.columns]
    return frame


def read_table_columns(
    table_name: str,
    settings: SqlServerConnectionSettings = SQL_SERVER_SETTINGS,
) -> list[str]:
    """Read SQL Server column names without materializing all rows."""
    query = f"SELECT TOP 0 * FROM {_qualified_table_name(table_name)}"
    with get_connection(settings) as connection:
        frame = pd.read_sql(query, connection)
    return [str(column).strip() for column in frame.columns]
