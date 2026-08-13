"""Cross-suite cleanup fixtures for process-global repository state."""

from collections.abc import Generator

import pytest

from greenlead.repositories import reset_repository


@pytest.fixture(autouse=True)
def close_repository_engine_after_test() -> Generator[None, None, None]:
    """Dispose the singleton SQL engine even when an assertion fails."""
    yield
    reset_repository()
