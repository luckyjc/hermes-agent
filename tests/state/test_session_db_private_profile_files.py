import os
import stat
from contextlib import contextmanager

import pytest

from hermes_state import SessionDB
import hermes_state_wal


pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX file mode semantics")


@contextmanager
def _umask(mask: int):
    previous = os.umask(mask)
    try:
        yield
    finally:
        os.umask(previous)


def _mode(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def _state_files(db_path):
    return (
        db_path,
        db_path.with_name(db_path.name + "-wal"),
        db_path.with_name(db_path.name + "-shm"),
    )


def _force_wal(monkeypatch):
    monkeypatch.setattr(
        hermes_state_wal, "is_sqlite_wal_reset_vulnerable", lambda version_info=None: False,
    )
    monkeypatch.setattr(hermes_state_wal, "resolve_journal_mode", lambda: "wal")


def test_session_db_creates_private_live_wal_state_files_under_permissive_umask(
    tmp_path, monkeypatch,
):
    _force_wal(monkeypatch)
    db_path = tmp_path / "state.db"

    with _umask(0o022):
        db = SessionDB(db_path=db_path)
    try:
        db.create_session("s1", source="cli")

        assert db._wal_active
        for path in _state_files(db_path):
            assert path.exists(), f"{path.name} was not created"
            assert _mode(path) == 0o600, f"{path.name} mode was {oct(_mode(path))}"
    finally:
        db.close()


def test_session_db_hardens_existing_owner_state_files(tmp_path, monkeypatch):
    _force_wal(monkeypatch)
    db_path = tmp_path / "state.db"
    with _umask(0o022):
        db = SessionDB(db_path=db_path)
        db.create_session("s1", source="cli")
        assert db._wal_active
        db.close()

    existing_paths = _state_files(db_path)
    for path in existing_paths:
        if not path.exists():
            path.touch()
        os.chmod(path, 0o644)

    reopened = SessionDB(db_path=db_path)
    try:
        for path in _state_files(db_path):
            assert path.exists(), f"{path.name} was not preserved"
            assert _mode(path) == 0o600, f"{path.name} mode was {oct(_mode(path))}"
    finally:
        reopened.close()


def test_session_db_refuses_owner_state_file_that_cannot_be_hardened(tmp_path, monkeypatch):
    _force_wal(monkeypatch)
    db_path = tmp_path / "state.db"
    db = SessionDB(db_path=db_path)
    db.close()
    os.chmod(db_path, 0o644)

    real_chmod = os.chmod

    def deny_state_db(path, mode, *, dir_fd=None, follow_symlinks=True):
        if os.fspath(path) == os.fspath(db_path):
            raise PermissionError("chmod denied by test")
        return real_chmod(path, mode, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(os, "chmod", deny_state_db)

    with pytest.raises(PermissionError, match="state.db.*0600"):
        SessionDB(db_path=db_path)


def test_session_db_refuses_silently_ineffective_state_file_hardening(tmp_path, monkeypatch):
    _force_wal(monkeypatch)
    db_path = tmp_path / "state.db"
    db = SessionDB(db_path=db_path)
    db.close()
    os.chmod(db_path, 0o644)

    real_chmod = os.chmod

    def ignore_state_db(path, mode, *, dir_fd=None, follow_symlinks=True):
        if os.fspath(path) == os.fspath(db_path):
            return None
        return real_chmod(path, mode, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(os, "chmod", ignore_state_db)

    with pytest.raises(PermissionError, match="state.db.*remains.*0644"):
        SessionDB(db_path=db_path)


def test_state_file_hardening_does_not_follow_a_raced_symlink(tmp_path, monkeypatch):
    _force_wal(monkeypatch)
    db_path = tmp_path / "state.db"
    db = SessionDB(db_path=db_path)
    db.close()
    os.chmod(db_path, 0o644)
    unrelated = tmp_path / "unrelated"
    unrelated.write_text("not sqlite", encoding="utf-8")
    os.chmod(unrelated, 0o644)

    real_chmod = os.chmod

    def race_state_db(path, mode, *, dir_fd=None, follow_symlinks=True):
        if os.fspath(path) == os.fspath(db_path):
            assert follow_symlinks is False
            db_path.unlink()
            db_path.symlink_to(unrelated)
        return real_chmod(path, mode, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(os, "chmod", race_state_db)

    with pytest.raises(PermissionError, match="state.db.*0600"):
        SessionDB(db_path=db_path)
    assert _mode(unrelated) == 0o644


def test_session_db_hardens_live_state_files_without_breaking_writer(tmp_path, monkeypatch):
    _force_wal(monkeypatch)
    db_path = tmp_path / "state.db"
    db = SessionDB(db_path=db_path)
    try:
        db.create_session("s1", source="cli")
        assert db._wal_active
        for path in _state_files(db_path):
            assert path.exists(), f"{path.name} was not created"
            os.chmod(path, 0o644)

        from hermes_state_dbfile import ensure_private_sqlite_state_files

        ensure_private_sqlite_state_files(db_path, connection_live=True)
        db.append_message("s1", "user", "still writable after hardening")

        assert [row["content"] for row in db.get_messages("s1")] == [
            "still writable after hardening"
        ]
        for path in _state_files(db_path):
            assert _mode(path) == 0o600, f"{path.name} mode was {oct(_mode(path))}"
    finally:
        db.close()
