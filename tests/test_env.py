from src.core import env


def test_foxflow_name_wins(monkeypatch):
    monkeypatch.setenv("FOXFLOW_LANG", "vi")
    monkeypatch.setenv("FOXPROFILE_LANG", "en")
    assert env.getenv("LANG") == "vi"


def test_foxprofile_name_still_works(monkeypatch):
    monkeypatch.delenv("FOXFLOW_LANG", raising=False)
    monkeypatch.setenv("FOXPROFILE_LANG", "vi")
    assert env.getenv("LANG", "en") == "vi"


def test_default_when_unset(monkeypatch):
    monkeypatch.delenv("FOXFLOW_LANG", raising=False)
    monkeypatch.delenv("FOXPROFILE_LANG", raising=False)
    assert env.getenv("LANG", "en") == "en"
    assert env.getenv("LANG") is None


def test_empty_value_counts_as_set(monkeypatch):
    monkeypatch.setenv("FOXFLOW_API_TOKEN", "")
    monkeypatch.setenv("FOXPROFILE_API_TOKEN", "legacy-token")
    assert env.getenv("API_TOKEN") == ""
