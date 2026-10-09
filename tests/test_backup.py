import shutil
import subprocess

import pytest
from django.core.management import CommandError, call_command
from django.db import connection

pytestmark = pytest.mark.django_db

needs_pg_dump = pytest.mark.skipif(not shutil.which("pg_dump"), reason="pg_dump not installed")


def _run(tmp_path, keep=14):
    call_command("backup_db", dir=str(tmp_path), keep=keep, stdout=open("/dev/null", "w"))


@needs_pg_dump
def test_dump_is_a_valid_archive(tmp_path):
    _run(tmp_path)
    [dump] = tmp_path.glob("*.dump")
    assert not list(tmp_path.glob("*.partial"))
    listing = subprocess.run(["pg_restore", "--list", str(dump)], capture_output=True, text=True)
    assert listing.returncode == 0
    assert "applications" in listing.stdout


@needs_pg_dump
def test_prunes_to_keep(tmp_path):
    name = connection.settings_dict["NAME"]
    for i in range(3):
        (tmp_path / f"{name}-20200101-00000{i}.dump").write_bytes(b"old")
    _run(tmp_path, keep=2)
    dumps = sorted(p.name for p in tmp_path.glob("*.dump"))
    assert len(dumps) == 2
    assert dumps[0] == f"{name}-20200101-000002.dump"


def test_missing_pg_dump(tmp_path, monkeypatch):
    monkeypatch.delenv("PG_DUMP", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(CommandError, match="pg_dump not found"):
        _run(tmp_path)


def test_failed_dump_leaves_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("PG_DUMP", "/bin/false")
    with pytest.raises(CommandError, match="pg_dump failed"):
        _run(tmp_path)
    assert not list(tmp_path.iterdir())
