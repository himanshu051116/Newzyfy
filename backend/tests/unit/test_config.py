import pytest
from pydantic import ValidationError

from newsintel.core.config import Settings


def test_ai_is_disabled_by_default() -> None:
    assert Settings(_env_file=None).ai_provider == "disabled"


def test_production_rejects_unsafe_defaults() -> None:
    with pytest.raises(ValidationError, match="unsafe production defaults"):
        Settings(environment="production", _env_file=None)

