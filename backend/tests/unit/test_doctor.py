from pydantic import SecretStr

from newsintel.core.config import Settings
from newsintel.doctor import database_target, tcp_reachable


def test_database_target_redacts_password() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://user:secret@db.example:5544/news",
        object_store_secret_key=SecretStr("test"),
        _env_file=None,
    )

    target = database_target(settings)

    assert target.host == "db.example"
    assert target.port == 5544
    assert "secret" not in target.redacted_url
    assert "***" in target.redacted_url


def test_closed_local_port_is_reported_unreachable() -> None:
    assert not tcp_reachable("127.0.0.1", 9, timeout_seconds=0.05)

