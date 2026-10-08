"""Data types shared by the providers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class MarketInfo:
    """One 15-minute BTC Up/Down window."""

    market_id: str  # condition id on Polymarket
    slug: str
    title: str
    condition_id: str
    yes_up_id: str  # token id of the "Up" outcome
    no_down_id: str  # token id of the "Down" outcome
    start_time: datetime
    end_time: datetime


@dataclass
class OrderbookLevel:
    price: float
    size: float


@dataclass
class OrderbookL1:
    """Best bid and best ask.  A price of 0.0 means that side of the book was empty."""

    asset_id: str
    side: str  # "yes" | "no"
    bid_price: float
    bid_size: float
    ask_price: float
    ask_size: float
    ts: datetime  # the book's own timestamp if the response had one, else receive time


@dataclass
class OrderbookL2:
    """Top N levels, best price first on both sides."""

    asset_id: str
    side: str
    bids: list[OrderbookLevel]
    asks: list[OrderbookLevel]
    ts: datetime


@dataclass
class SpotPrice:
    """BTC/USD reference price."""

    price: float
    ts: datetime
    source: str
