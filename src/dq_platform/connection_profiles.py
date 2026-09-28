"""Named SQL Server connection profiles for the notebook UI.

Profiles let a user save "server + database (+ auth mode)" combinations under
a friendly name and reuse them across sessions, so the UI can connect to more
than one server/database instead of only the fixed defaults in
:mod:`dq_platform.connection`.

Only Windows-authenticated (trusted) or username-only metadata is persisted.
Passwords are **never** written to disk; if SQL authentication is used the
password must be supplied again each session and is kept in memory only.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from dq_platform.connection import SqlServerConnectionSettings

_DEFAULT_PROFILE_STORE = Path.home() / ".dq_platform" / "connections.json"


@dataclass(frozen=True)
class ConnectionProfile:
    """A saved, non-secret SQL Server connection profile."""

    name: str
    driver: str = "ODBC Driver 18 for SQL Server"
    server: str = ""
    database: str = ""
    trusted_connection: bool = True
    username: Optional[str] = None
    authentication: Optional[str] = None
    encrypt: bool = False
    trust_server_certificate: bool = True
    connection_timeout_seconds: int = 30

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "ConnectionProfile":
        known_fields = {f.name for f in ConnectionProfile.__dataclass_fields__.values()}
        cleaned = {key: value for key, value in data.items() if key in known_fields}
        return ConnectionProfile(**cleaned)


def _store_path(store_path: Optional[Path] = None) -> Path:
    return store_path or _DEFAULT_PROFILE_STORE


def load_profiles(store_path: Optional[Path] = None) -> dict[str, ConnectionProfile]:
    """Load all saved connection profiles, keyed by profile name."""
    path = _store_path(store_path)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    profiles: dict[str, ConnectionProfile] = {}
    for entry in raw.get("profiles", []):
        try:
            profile = ConnectionProfile.from_dict(entry)
        except TypeError:
            continue
        profiles[profile.name] = profile
    return profiles


def list_profile_names(store_path: Optional[Path] = None) -> list[str]:
    return sorted(load_profiles(store_path).keys())


def save_profile(profile: ConnectionProfile, store_path: Optional[Path] = None) -> None:
    """Add or replace a profile (keyed by name) in the on-disk store."""
    if not str(profile.name or "").strip():
        raise ValueError("Connection profile name must not be empty.")

    path = _store_path(store_path)
    profiles = load_profiles(path)
    profiles[profile.name] = profile

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"profiles": [item.to_dict() for item in profiles.values()]}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def delete_profile(name: str, store_path: Optional[Path] = None) -> bool:
    """Remove a profile by name. Returns True if a profile was removed."""
    path = _store_path(store_path)
    profiles = load_profiles(path)
    if name not in profiles:
        return False
    del profiles[name]

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"profiles": [item.to_dict() for item in profiles.values()]}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return True


def profile_to_settings(
    profile: ConnectionProfile, password: Optional[str] = None
) -> SqlServerConnectionSettings:
    """Build session-only connection settings from a saved profile.

    ``password`` is accepted purely as an in-memory parameter for optional
    SQL authentication; it is never read from or written to the profile
    store.
    """
    return SqlServerConnectionSettings(
        driver=profile.driver,
        server=profile.server,
        database=profile.database,
        username=profile.username,
        password=password,
        authentication=profile.authentication,
        trusted_connection=profile.trusted_connection,
        encrypt=profile.encrypt,
        trust_server_certificate=profile.trust_server_certificate,
        connection_timeout_seconds=profile.connection_timeout_seconds,
    )
