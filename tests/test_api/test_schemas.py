import pytest
from pydantic import ValidationError

from backend.api.schemas import GenerateRequest


def test_generate_request_requires_non_empty_prompt() -> None:
    with pytest.raises(ValidationError):
        GenerateRequest(prompt="   ")


def test_generate_request_enforces_max_length() -> None:
    with pytest.raises(ValidationError):
        GenerateRequest(prompt="x" * 5001)
