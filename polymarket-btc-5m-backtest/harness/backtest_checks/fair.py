"""A log-normal fair value for an up/down window."""

from __future__ import annotations

import math


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def fair_p_up(spot: float, start_price: float, sigma: float, t_left: float) -> float:
    """P(final price >= start price | price now), zero drift.

    `sigma` is the standard deviation of log returns per second and `t_left` the seconds
    left in the window.  At or after the end the answer is 1 or 0.  Without a usable
    sigma or prices the model has no opinion and returns 0.5.
    """
    if t_left <= 0:
        return 1.0 if spot >= start_price else 0.0
    if sigma <= 0 or spot <= 0 or start_price <= 0:
        return 0.5
    z = math.log(spot / start_price) / (sigma * math.sqrt(t_left))
    return norm_cdf(z)
