"""Hand-made markets for the tests.  All values are synthetic."""

from backtest_checks.model import Market, Tick

T0 = 1_767_225_600.0  # 2026-01-01 00:00:00 UTC


def tick(i, spot=100.0, ya=0.50, na=0.52, yb=0.48, nb=0.50, ys=100.0, ns=100.0, sigma=0.001, start=T0):
    return Tick(t=start + i, spot=spot, sigma=sigma, yes_bid=yb, yes_ask=ya, no_bid=nb, no_ask=na,
                yes_ask_size=ys, no_ask_size=ns)


def market(ticks, outcome="YES", start=T0, start_price=100.0, mid="m-1"):
    return Market(market_id=mid, start=start, end=start + 300, start_price=start_price,
                  ticks=list(ticks), outcome=outcome)


def flat_market(outcome="YES", start=T0, mid="m-1", n=300, **kw):
    """n ticks, one a second from the window start, all with the same quotes."""
    return market([tick(i, start=start, **kw) for i in range(n)], outcome=outcome, start=start, mid=mid)
