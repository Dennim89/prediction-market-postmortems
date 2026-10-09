"""Shared synthetic data for the tests: 24 hours from updown_audit.synthetic."""

import pytest

from updown_audit import db, synthetic


@pytest.fixture(scope="session")
def frames24():
    return synthetic.generate(hours=24, seed=1)


@pytest.fixture(scope="session")
def con24(frames24):
    con = db.connect()
    db.load_frames(con, **frames24)
    yield con
    con.close()
