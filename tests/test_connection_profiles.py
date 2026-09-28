from pathlib import Path

import pytest

from dq_platform.connection_profiles import (
    ConnectionProfile,
    delete_profile,
    list_profile_names,
    load_profiles,
    profile_to_settings,
    save_profile,
)


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    return tmp_path / "connections.json"


def test_save_and_load_profile_round_trip(store_path: Path):
    profile = ConnectionProfile(
        name="Prod-mart6",
        server="mart6.its.hpecorp.net",
        database="TPM_winback",
        trusted_connection=True,
    )
    save_profile(profile, store_path)

    profiles = load_profiles(store_path)

    assert "Prod-mart6" in profiles
    assert profiles["Prod-mart6"].server == "mart6.its.hpecorp.net"
    assert profiles["Prod-mart6"].database == "TPM_winback"
    assert list_profile_names(store_path) == ["Prod-mart6"]


def test_save_profile_replaces_existing_entry_with_same_name(store_path: Path):
    save_profile(ConnectionProfile(name="Dev", server="server1", database="db1"), store_path)
    save_profile(ConnectionProfile(name="Dev", server="server2", database="db2"), store_path)

    profiles = load_profiles(store_path)

    assert len(profiles) == 1
    assert profiles["Dev"].server == "server2"
    assert profiles["Dev"].database == "db2"


def test_save_profile_rejects_empty_name(store_path: Path):
    with pytest.raises(ValueError, match="must not be empty"):
        save_profile(ConnectionProfile(name="   "), store_path)


def test_delete_profile_removes_entry_and_reports_result(store_path: Path):
    save_profile(ConnectionProfile(name="Temp", server="server1", database="db1"), store_path)

    assert delete_profile("Temp", store_path) is True
    assert load_profiles(store_path) == {}
    assert delete_profile("Temp", store_path) is False


def test_load_profiles_returns_empty_dict_when_store_missing(store_path: Path):
    assert load_profiles(store_path) == {}


def test_profile_to_settings_never_persists_password(store_path: Path):
    profile = ConnectionProfile(
        name="SqlAuth",
        server="server1",
        database="db1",
        trusted_connection=False,
        username="demo-user",
    )
    save_profile(profile, store_path)

    settings = profile_to_settings(profile, password="in-memory-only")

    assert settings.username == "demo-user"
    assert settings.password == "in-memory-only"
    assert "password" not in store_path.read_text(encoding="utf-8")
    assert "in-memory-only" not in store_path.read_text(encoding="utf-8")
