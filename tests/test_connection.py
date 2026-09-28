import pytest

import dq_platform.connection as connection_module
from dq_platform.connection import SqlServerConnectionSettings


def test_connection_settings_defaults_match_seed_notebook():
    settings = SqlServerConnectionSettings()
    connection_string = settings.to_connection_string()

    assert "DRIVER={ODBC Driver 18 for SQL Server}" in connection_string
    assert "SERVER=mart6.its.hpecorp.net" in connection_string
    assert "DATABASE=TPM_winback" in connection_string
    assert "Trusted_Connection=yes" in connection_string
    assert "Encrypt=no" in connection_string
    assert "TrustServerCertificate=yes" in connection_string
    assert "Connection Timeout=30" in connection_string


def test_connection_settings_support_sql_auth_without_changing_defaults():
    settings = SqlServerConnectionSettings(
        username="demo-user",
        password="demo-pass",
        trusted_connection=False,
    )
    connection_string = settings.to_connection_string()

    assert "UID=demo-user" in connection_string
    assert "PWD=demo-pass" in connection_string
    assert "******" not in connection_string
    assert "Trusted_Connection=yes" not in connection_string


def test_connection_string_rejects_partial_sql_credentials():
    settings = SqlServerConnectionSettings(
        username="demo-user",
        password=None,
        trusted_connection=False,
    )

    with pytest.raises(ValueError, match="Provide both DQ_SQL_USERNAME and DQ_SQL_PASSWORD"):
        settings.to_connection_string()


def test_get_connection_surfaces_actionable_message_for_sspi_errors(monkeypatch):
    settings = SqlServerConnectionSettings(
        trusted_connection=True,
        username=None,
        password=None,
    )

    def _raise_sspi(_connection_string):
        raise connection_module.pyodbc.Error("Cannot generate SSPI context")

    monkeypatch.setattr(connection_module.pyodbc, "connect", _raise_sspi)

    with pytest.raises(ConnectionError, match="DQ_SQL_TRUSTED_CONNECTION=false"):
        connection_module.get_connection(settings)
