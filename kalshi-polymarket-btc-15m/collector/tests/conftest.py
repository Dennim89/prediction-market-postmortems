"""Shared fixtures.  The JSON files in fixtures/ are synthetic and written by hand; they
follow the response shapes the code expects, not captures of the live API."""

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def gamma_events():
    return _load("gamma_events.json")


@pytest.fixture
def clob_book():
    return _load("clob_book.json")


@pytest.fixture
def rtds_messages():
    return _load("rtds_messages.json")
