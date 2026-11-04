import pytest

from emporio import tools


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    monkeypatch.setenv("EMPORIO_STATE_DIR", str(tmp_path))
    monkeypatch.setattr("emporio.config.STATE_DIR", tmp_path)
    monkeypatch.setenv("EMPORIO_NOW", "2026-02-20T10:00:00")
    tools.reset_rate_limit()
    yield
