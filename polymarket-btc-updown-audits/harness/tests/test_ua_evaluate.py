import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from ua_helpers import ts

from updown_audit import evaluate, signals


def trades(rows):
    """rows: (entry minute, price, won, min bid after)."""
    return pd.DataFrame([{"market_id": f"m{i}", "entry_ts": ts(minute), "entry_price": p, "won": w,
                          "min_bid_after": b} for i, (minute, p, w, b) in enumerate(rows)])


def test_fee_formula():
    assert evaluate.fee_per_share(0.5, 0.10) == pytest.approx(0.025)
    assert evaluate.fee_per_share(0.9, 0.10) == pytest.approx(0.009)


def test_hold_to_expiry_pays_one_fee():
    t = evaluate.per_share(trades([(0, 0.8, True, 0.7), (1, 0.6, False, 0.1)]), fee_rate=0.10)
    assert t["gross"].tolist() == pytest.approx([0.2, -0.6])
    assert t["fee"].tolist() == pytest.approx([0.016, 0.024])
    assert t["net"].tolist() == pytest.approx([0.184, -0.624])
    assert not t["stopped"].any()


def test_a_stop_sells_at_the_stop_and_pays_a_second_fee():
    t = evaluate.per_share(trades([(0, 0.8, True, 0.60), (1, 0.8, True, 0.70), (2, 0.8, False, np.nan)]),
                           fee_rate=0.10, stop=0.15)
    assert t["stopped"].tolist() == [True, False, False]
    assert t.loc[0, "gross"] == pytest.approx(-0.15)
    assert t.loc[0, "fee"] == pytest.approx(0.016 + 0.10 * 0.65 * 0.35)
    assert t.loc[1, "gross"] == pytest.approx(0.2)  # never fell below 0.65
    assert t.loc[2, "gross"] == pytest.approx(-0.8)  # no bid seen after entry: no stop


def test_evaluate_splits_by_time_and_divides_by_period_length():
    t = trades([(0, 0.5, True, 0.4), (60, 0.5, True, 0.4), (60 * 30, 0.5, False, 0.4)])
    out = evaluate.evaluate(t, fee_rate=0.0, split_at=ts(60 * 24), start=ts(0), end=ts(60 * 36)).set_index("part")
    assert out.loc["train", "trades"] == 2 and out.loc["test", "trades"] == 1
    assert out.loc["train", "days"] == pytest.approx(1.0) and out.loc["test", "days"] == pytest.approx(0.5)
    assert out.loc["train", "net_per_day"] == pytest.approx(1.0)  # +0.5 twice in one day
    assert out.loc["test", "net_per_day"] == pytest.approx(-1.0)  # -0.5 in half a day
    assert out.loc["all", "hit"] == pytest.approx(2 / 3)


def test_fees_of_gross_and_weights():
    t = trades([(0, 0.5, True, 0.4), (1, 0.5, False, 0.4), (2, 0.5, True, 0.4)])
    flat = evaluate.evaluate(t, 0.10, split_at=ts(10)).set_index("part")
    assert flat.loc["all", "gross_per_share"] == pytest.approx(0.5 / 3)
    assert flat.loc["all", "fees_of_gross"] == pytest.approx(0.025 * 3 / 0.5)
    sized = evaluate.evaluate(t, 0.10, split_at=ts(10), shares=pd.Series([2.0, 0.0, 1.0])).set_index("part")
    assert sized.loc["all", "trades"] == 2 and sized.loc["all", "shares"] == 3
    assert sized.loc["all", "net_per_share"] == pytest.approx(0.5 - 0.025)
    losing = evaluate.evaluate(t.assign(won=False), 0.10, split_at=ts(10)).set_index("part")
    assert np.isnan(losing.loc["all", "fees_of_gross"])


def test_subsample_is_reproducible_and_seed_dependent():
    t = trades([(i, 0.5, bool(i % 2), 0.4) for i in range(400)])
    a, b, c = (evaluate.subsample(t, s) for s in (1, 1, 2))
    assert a["market_id"].tolist() == b["market_id"].tolist()
    assert a["market_id"].tolist() != c["market_id"].tolist()
    assert 0.7 < len(a) / len(t) < 0.9


def test_subsample_does_not_depend_on_the_process_hash_seed():
    code = ("import pandas as pd; from updown_audit.evaluate import subsample;"
            "t = pd.DataFrame({'market_id': [f'm{i}' for i in range(50)], 'entry_ts': range(50)});"
            "print(','.join(subsample(t, 3)['market_id']))")
    root = str(Path(__file__).resolve().parents[1])
    outputs = set()
    for hash_seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": hash_seed,
               "PYTHONPATH": root + os.pathsep + os.environ.get("PYTHONPATH", "")}
        outputs.add(subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                                   check=True).stdout)
    assert len(outputs) == 1


def test_bucket_sizing_follows_the_fitted_buckets():
    fit_on = pd.DataFrame({"slot": [1, 1, 1, 2, 2, 2, 3], "side": ["Up"] * 7,
                           "entry_price": [0.71, 0.72, 0.73, 0.81, 0.82, 0.83, 0.91],
                           "won": [True, True, True, False, False, False, True]})
    sizing = evaluate.fit_bucket_sizing(fit_on, fee_rate=0.0, max_shares=3, min_trades=3)
    new = pd.DataFrame({"slot": [1, 2, 3, 1], "side": ["Up"] * 4, "entry_price": [0.75, 0.85, 0.95, 0.55]})
    assert sizing(new).tolist() == [3.0, 0.0, 1.0, 1.0]  # good, bad, too few, unseen


def test_sizing_fitted_on_all_data_flatters_the_test_part(con24):
    pins = signals.pin_trades(signals.pin_candidates(con24), threshold=0.9)
    split_at = pins["entry_ts"].min() + pd.Timedelta(hours=12)
    out = evaluate.sizing_check(pins, 0.10, split_at).set_index("variant")
    in_sample = out.loc["sized, fitted on all data", "test_net_per_share"]
    honest = out.loc["sized, fitted on train only", "test_net_per_share"]
    assert in_sample > honest + 0.02
    flat = evaluate.evaluate(pins, 0.10, split_at).set_index("part")
    assert out.loc["flat, one share", "test_net_per_share"] == pytest.approx(flat.loc["test", "net_per_share"])
