"""Configuration: built-in defaults, then config.yaml, then environment variables.

Environment variables win over config.yaml.  Every setting has a default, so the
collector runs with no configuration at all.  No setting is secret: the collector
only reads public endpoints.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PolymarketConfig(_Section):
    """Public, read-only Polymarket endpoints."""

    gamma_url: str = "https://gamma-api.polymarket.com"
    clob_url: str = "https://clob.polymarket.com"
    rtds_url: str = "wss://ws-live-data.polymarket.com"
    bitcoin_tag_id: str = "235"


class OutputConfig(_Section):
    dir: str = "./data"
    raw_subdir: str = "raw"
    ticks_subdir: str = "ticks"


class IntervalsConfig(_Section):
    """Polling intervals and tolerances, in seconds."""

    tick_interval_sec: float = Field(5.0, gt=0)
    orderbook_poll_sec: float = Field(1.0, gt=0)
    spot_poll_sec: float = Field(2.0, gt=0)
    market_discovery_sec: float = Field(10.0, gt=0)
    # The open price is taken only from a price stamped at most this long after the
    # window start.  A later price is not the open, so the window gets no open price.
    open_price_max_lag_sec: float = Field(5.0, ge=0)


class OrderbookConfig(_Section):
    l2_depth: int = Field(10, gt=0)


class CollectorConfig(_Section):
    polymarket: PolymarketConfig = Field(default_factory=PolymarketConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    intervals: IntervalsConfig = Field(default_factory=IntervalsConfig)
    orderbook: OrderbookConfig = Field(default_factory=OrderbookConfig)
    # "mock" providers produce synthetic data and make no network calls.
    market_provider: Literal["polymarket", "mock"] = "polymarket"
    spot_provider: Literal["rtds", "mock"] = "rtds"
    log_level: str = "INFO"


# Environment variable -> (section, field); section None means a top-level field.
ENV_VARS: dict[str, tuple[str | None, str]] = {
    "MARKET_PROVIDER": (None, "market_provider"),
    "SPOT_PROVIDER": (None, "spot_provider"),
    "LOG_LEVEL": (None, "log_level"),
    "POLYMARKET_GAMMA_URL": ("polymarket", "gamma_url"),
    "POLYMARKET_CLOB_URL": ("polymarket", "clob_url"),
    "POLYMARKET_RTDS_URL": ("polymarket", "rtds_url"),
    "POLYMARKET_BITCOIN_TAG_ID": ("polymarket", "bitcoin_tag_id"),
    "OUTPUT_DIR": ("output", "dir"),
    "TICK_INTERVAL_SEC": ("intervals", "tick_interval_sec"),
    "ORDERBOOK_POLL_SEC": ("intervals", "orderbook_poll_sec"),
    "SPOT_POLL_SEC": ("intervals", "spot_poll_sec"),
    "MARKET_DISCOVERY_SEC": ("intervals", "market_discovery_sec"),
    "OPEN_PRICE_MAX_LAG_SEC": ("intervals", "open_price_max_lag_sec"),
    "L2_DEPTH": ("orderbook", "l2_depth"),
}

_YAML_SECTIONS = ("polymarket", "output", "intervals", "orderbook")
_YAML_KEYS = set(_YAML_SECTIONS) | {"providers", "logging"}


def _from_yaml(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Map the config.yaml layout onto CollectorConfig fields."""
    unknown = set(raw) - _YAML_KEYS
    if unknown:
        raise ValueError(f"unknown config.yaml sections: {sorted(unknown)}")
    data: dict[str, Any] = {}
    for section in _YAML_SECTIONS:
        if raw.get(section) is not None:
            data[section] = dict(raw[section])
    providers = raw.get("providers") or {}
    if "market" in providers:
        data["market_provider"] = providers["market"]
    if "spot" in providers:
        data["spot_provider"] = providers["spot"]
    logging_section = raw.get("logging") or {}
    if "level" in logging_section:
        data["log_level"] = logging_section["level"]
    return data


def load_config(
    config_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> CollectorConfig:
    """Load the configuration.

    If `config_path` is None, ./config.yaml is used when it exists.  A path that was
    passed explicitly must exist.  Environment variables override the file.
    """
    environ = os.environ if environ is None else environ
    data: dict[str, Any] = {}

    path = Path(config_path) if config_path else Path("config.yaml")
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: expected a mapping at the top level")
        data = _from_yaml(raw)
    elif config_path:
        raise FileNotFoundError(f"config file not found: {path}")

    for name, (section, field) in ENV_VARS.items():
        value = environ.get(name)
        if value is None or value == "":
            continue
        if section is None:
            data[field] = value
        else:
            data.setdefault(section, {})[field] = value

    return CollectorConfig.model_validate(data)
