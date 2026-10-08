"""Configuration: defaults, config.yaml, environment variables."""

from pathlib import Path

import pytest

from collector.config import CollectorConfig, load_config

EXAMPLE = Path(__file__).resolve().parents[1] / "config.yaml.example"


def test_defaults_without_file_or_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = load_config(environ={})
    assert cfg == CollectorConfig()
    assert (cfg.market_provider, cfg.spot_provider) == ("polymarket", "rtds")


def test_example_file_holds_the_defaults():
    assert load_config(EXAMPLE, environ={}) == CollectorConfig()


def test_environment_overrides_yaml(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "providers:\n  market: mock\n  spot: rtds\n"
        "intervals:\n  tick_interval_sec: 3\n"
        "output:\n  dir: ./from-yaml\n",
        encoding="utf-8",
    )
    cfg = load_config(path, environ={"SPOT_PROVIDER": "mock", "TICK_INTERVAL_SEC": "0.5", "OUTPUT_DIR": ""})
    assert cfg.market_provider == "mock"  # from the file
    assert cfg.spot_provider == "mock"  # the environment wins
    assert cfg.intervals.tick_interval_sec == 0.5
    assert cfg.output.dir == "./from-yaml"  # an empty variable is ignored
    assert cfg.intervals.orderbook_poll_sec == 1.0  # default kept


def test_bad_values_fail_early(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        load_config(environ={"MARKET_PROVIDER": "kalshi"})
    with pytest.raises(ValueError):
        load_config(environ={"TICK_INTERVAL_SEC": "0"})
    typo = tmp_path / "typo.yaml"
    typo.write_text("intervals:\n  tick_interval: 5\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(typo, environ={})
    section = tmp_path / "section.yaml"
    section.write_text("polymarkt:\n  clob_url: https://clob.test\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(section, environ={})


def test_a_named_config_file_must_exist(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "missing.yaml", environ={})
