"""Reusable ipywidgets panel for configuring a SQL Server connection.

Lets the notebook UI point at different servers/databases (not just the
fixed defaults in :mod:`dq_platform.connection`), and save/reuse named
connection profiles. Windows authentication is the primary path, so no
password is ever written to disk; a SQL-auth password (if used) is kept in
memory for the current session only.
"""

from __future__ import annotations

import html
from typing import Callable, Optional

import ipywidgets as widgets

from dq_platform.connection import SQL_SERVER_SETTINGS, SqlServerConnectionSettings, get_connection
from dq_platform.connection_profiles import (
    ConnectionProfile,
    delete_profile,
    load_profiles,
    profile_to_settings,
    save_profile,
)

_STYLE = {"description_width": "150px"}
_WIDE = widgets.Layout(width="420px")

_DEFAULT_PROFILE_LABEL = "Default (from connection.py)"


def _style() -> dict[str, str]:
    return dict(_STYLE)


class ConnectionPanel:
    """Stateful widget group for choosing/saving a SQL Server connection."""

    def __init__(self, title: str = "SQL Server connection", on_change: Optional[Callable[[], None]] = None):
        self._on_change = on_change
        self._session_password: Optional[str] = None
        self._profiles: dict[str, ConnectionProfile] = {}

        self.profile_dropdown = widgets.Dropdown(
            description="Saved profile", options=[_DEFAULT_PROFILE_LABEL], style=_style(), layout=_WIDE
        )
        self.server_box = widgets.Text(
            description="Server", value=SQL_SERVER_SETTINGS.server, style=_style(), layout=_WIDE
        )
        self.database_box = widgets.Text(
            description="Database", value=SQL_SERVER_SETTINGS.database, style=_style(), layout=_WIDE
        )
        self.driver_box = widgets.Text(
            description="Driver", value=SQL_SERVER_SETTINGS.driver, style=_style(), layout=_WIDE
        )
        self.auth_toggle = widgets.ToggleButtons(
            description="Auth mode",
            options=[("Windows (trusted)", "trusted"), ("SQL login", "sql")],
            value="trusted" if SQL_SERVER_SETTINGS.trusted_connection else "sql",
            style=_style(),
            layout=_WIDE,
        )
        self.username_box = widgets.Text(
            description="Username",
            value=SQL_SERVER_SETTINGS.username or "",
            style=_style(),
            layout=_WIDE,
            disabled=SQL_SERVER_SETTINGS.trusted_connection,
        )
        self.password_box = widgets.Password(
            description="Password (session only)",
            style=_style(),
            layout=_WIDE,
            disabled=SQL_SERVER_SETTINGS.trusted_connection,
        )
        self.profile_name_box = widgets.Text(
            description="Profile name",
            placeholder="e.g. Prod-mart6",
            style=_style(),
            layout=_WIDE,
        )
        self.save_button = widgets.Button(description="Save profile", icon="save")
        self.delete_button = widgets.Button(description="Delete profile", icon="trash")
        self.test_button = widgets.Button(description="Test connection", icon="plug")
        self.status = widgets.HTML()

        self.panel = widgets.VBox(
            [
                widgets.HTML(
                    f"<div style='color:#5f6b6d;font-size:13px;margin-bottom:4px'>{html.escape(title)}"
                    "</div>"
                ),
                self.profile_dropdown,
                self.server_box,
                self.database_box,
                self.driver_box,
                self.auth_toggle,
                widgets.HBox([self.username_box, self.password_box]),
                widgets.HBox([self.profile_name_box, self.save_button, self.delete_button, self.test_button]),
                self.status,
            ]
        )

        self.profile_dropdown.observe(self._on_profile_selected, names="value")
        self.auth_toggle.observe(self._on_auth_mode_change, names="value")
        self.save_button.on_click(self._on_save_profile)
        self.delete_button.on_click(self._on_delete_profile)
        self.test_button.on_click(self._on_test_connection)
        for box in (self.server_box, self.database_box, self.driver_box, self.username_box, self.password_box):
            box.observe(self._on_field_change, names="value")

        self._refresh_profile_options()

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _error(message: str) -> str:
        return f"<span style='color:#b00020'><b>Error:</b> {html.escape(message)}</span>"

    @staticmethod
    def _ok(message: str) -> str:
        return f"<span style='color:#00674f'>{html.escape(message)}</span>"

    def _refresh_profile_options(self, select: Optional[str] = None) -> None:
        self._profiles = load_profiles()
        options = [_DEFAULT_PROFILE_LABEL, *sorted(self._profiles)]
        current = select or self.profile_dropdown.value
        self.profile_dropdown.unobserve(self._on_profile_selected, names="value")
        self.profile_dropdown.options = options
        self.profile_dropdown.value = current if current in options else _DEFAULT_PROFILE_LABEL
        self.profile_dropdown.observe(self._on_profile_selected, names="value")

    def _on_profile_selected(self, _change=None) -> None:
        selected = str(self.profile_dropdown.value or "")
        if selected == _DEFAULT_PROFILE_LABEL:
            settings = SQL_SERVER_SETTINGS
            self.profile_name_box.value = ""
        else:
            profile = self._profiles.get(selected)
            if profile is None:
                return
            settings = profile_to_settings(profile)
            self.profile_name_box.value = profile.name

        self.server_box.value = settings.server
        self.database_box.value = settings.database
        self.driver_box.value = settings.driver
        self.auth_toggle.value = "trusted" if settings.trusted_connection else "sql"
        self.username_box.value = settings.username or ""
        self.password_box.value = ""
        self._session_password = None
        self.status.value = ""
        self._notify_change()

    def _on_auth_mode_change(self, _change=None) -> None:
        trusted = self.auth_toggle.value == "trusted"
        self.username_box.disabled = trusted
        self.password_box.disabled = trusted
        if trusted:
            self.password_box.value = ""
            self._session_password = None
        self._notify_change()

    def _on_field_change(self, change=None) -> None:
        if change is not None and change.get("owner") is self.password_box:
            self._session_password = str(self.password_box.value or "") or None
        self._notify_change()

    def _notify_change(self) -> None:
        if self._on_change is not None:
            self._on_change()

    def _build_profile(self) -> ConnectionProfile:
        name = str(self.profile_name_box.value or "").strip()
        return ConnectionProfile(
            name=name,
            driver=str(self.driver_box.value or "").strip() or "ODBC Driver 18 for SQL Server",
            server=str(self.server_box.value or "").strip(),
            database=str(self.database_box.value or "").strip(),
            trusted_connection=self.auth_toggle.value == "trusted",
            username=str(self.username_box.value or "").strip() or None,
        )

    def _on_save_profile(self, _button=None) -> None:
        try:
            profile = self._build_profile()
            save_profile(profile)
        except Exception as exc:
            self.status.value = self._error(str(exc))
            return
        self._refresh_profile_options(select=profile.name)
        self.status.value = self._ok(f"Saved profile '{profile.name}'.")

    def _on_delete_profile(self, _button=None) -> None:
        name = str(self.profile_name_box.value or "").strip()
        if not name:
            self.status.value = self._error("Enter the profile name to delete.")
            return
        removed = delete_profile(name)
        self._refresh_profile_options()
        if removed:
            self.status.value = self._ok(f"Deleted profile '{name}'.")
        else:
            self.status.value = self._error(f"No saved profile named '{name}'.")

    def _on_test_connection(self, _button=None) -> None:
        self.status.value = "<span style='color:#5f6b6d'>Testing connection…</span>"
        try:
            with get_connection(self.current_settings()):
                pass
        except Exception as exc:
            self.status.value = self._error(str(exc))
            return
        self.status.value = self._ok("Connection succeeded.")

    # ------------------------------------------------------------------ API

    def current_settings(self) -> SqlServerConnectionSettings:
        trusted = self.auth_toggle.value == "trusted"
        return SqlServerConnectionSettings(
            driver=str(self.driver_box.value or "").strip() or "ODBC Driver 18 for SQL Server",
            server=str(self.server_box.value or "").strip(),
            database=str(self.database_box.value or "").strip(),
            username=None if trusted else (str(self.username_box.value or "").strip() or None),
            password=None if trusted else self._session_password,
            trusted_connection=trusted,
        )
