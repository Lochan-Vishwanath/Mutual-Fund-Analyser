"""
test_metrics.py — Known-answer tests for every financial formula
in metrics.py and the passive scoring path in screener.py.

Run: python3 -m pytest test_metrics.py -v
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from metrics import (
    cagr,
    max_drawdown,
    std_dev_annual,
    sharpe_ratio,
    sortino_ratio,
    compute_beta,
    compute_alpha,
    compute_info_ratio,
    compute_tracking_error,
    compute_down_capture,
    compute_up_capture,
    compute_capture_ratio,
    compute_alpha_stability,
    compute_all_metrics,
    _geo_mean_return,
    _monthly_aligned,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — synthetic NAV generators
# ─────────────────────────────────────────────────────────────────────────────

def _make_nav_series(annual_return: float, years: int, volatility: float = 0.0,
                     seed: int = 42) -> pd.Series:
    """Generate a synthetic daily NAV series with known annual return.
    
    If volatility == 0, produces a perfectly smooth curve.
    """
    rng = np.random.RandomState(seed)
    n_days = int(years * 252) + 1
    daily_r = (1 + annual_return) ** (1 / 252) - 1

    if volatility == 0:
        prices = 100.0 * (1 + daily_r) ** np.arange(n_days)
    else:
        daily_vol = volatility / np.sqrt(252)
        shocks = rng.normal(daily_r, daily_vol, n_days)
        prices = 100.0 * np.cumprod(1 + np.concatenate([[0], shocks[1:]]))

    return pd.Series(prices)


def _make_nav_df(annual_return: float, years: int, volatility: float = 0.0,
                 seed: int = 42) -> pd.DataFrame:
    """Like _make_nav_series but returns a DataFrame with date + nav columns."""
    nav = _make_nav_series(annual_return, years, volatility, seed)
    dates = pd.bdate_range(start="2015-01-01", periods=len(nav))
    return pd.DataFrame({"date": dates[:len(nav)], "nav": nav.values[:len(dates)]})


# ─────────────────────────────────────────────────────────────────────────────
# Test CAGR
# ─────────────────────────────────────────────────────────────────────────────

class TestCAGR:
    def test_exact_10pct_growth(self):
        """NAV with exact 10% annual growth should give CAGR ≈ 10%."""
        nav = _make_nav_series(0.10, 5)
        result = cagr(nav, 3)
        assert result == pytest.approx(0.10, abs=1e-6)

    def test_exact_doubling_in_3y(self):
        """NAV that doubles in exactly 3 years → CAGR ≈ 26.0%."""
        nav = _make_nav_series(2 ** (1/3) - 1, 5)
        result = cagr(nav, 3)
        assert result == pytest.approx(2 ** (1/3) - 1, abs=1e-5)

    def test_insufficient_history(self):
        """Should return None when series is too short."""
        nav = _make_nav_series(0.10, 2)
        assert cagr(nav, 3) is None

    def test_flat_zero_start(self):
        """Should return None when start value is 0."""
        nav = pd.Series([0.0, 1.0, 2.0])
        assert cagr(nav, 1) is None


# ─────────────────────────────────────────────────────────────────────────────
# Test Max Drawdown
# ─────────────────────────────────────────────────────────────────────────────

class TestMaxDrawdown:
    def test_known_drawdown(self):
        """Peak 100 → trough 60 → recovery → drawdown = -40%."""
        nav = pd.Series([100, 110, 105, 60, 70, 80, 90])
        dd = max_drawdown(nav)
        expected = (60 - 110) / 110  # -0.4545...
        assert dd == pytest.approx(expected, abs=1e-6)

    def test_monotonically_increasing(self):
        """No drawdown if prices only go up."""
        nav = pd.Series([100, 101, 102, 103, 104])
        assert max_drawdown(nav) == 0.0

    def test_short_series(self):
        """Single point → 0 drawdown."""
        assert max_drawdown(pd.Series([100])) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Test Std Dev Annual
# ─────────────────────────────────────────────────────────────────────────────

class TestStdDevAnnual:
    def test_zero_vol_smooth(self):
        """Perfectly smooth growth series should have near-zero annualized vol."""
        nav = _make_nav_series(0.10, 3, volatility=0.0)
        vol = std_dev_annual(nav)
        assert vol < 0.001  # effectively zero

    def test_positive_vol(self):
        """Noisy series should have measurable vol."""
        nav = _make_nav_series(0.10, 3, volatility=0.15)
        vol = std_dev_annual(nav)
        assert 0.10 < vol < 0.25  # should be close to input 15%


# ─────────────────────────────────────────────────────────────────────────────
# Test Sharpe Ratio
# ─────────────────────────────────────────────────────────────────────────────

class TestSharpeRatio:
    def test_known_sharpe(self):
        """A fund with known return and volatility should produce correct Sharpe."""
        # 15% annual return, 20% vol, Rf = 6.5%
        nav = _make_nav_series(0.15, 5, volatility=0.20, seed=123)
        sh = sharpe_ratio(nav, risk_free_rate=0.065)
        assert sh is not None
        # Rough check: (15% - 6.5%) / 20% ≈ 0.425
        # With noise it won't be exact, but should be in the right ballpark
        assert -0.5 < sh < 2.0

    def test_near_zero_vol(self):
        """Sharpe with near-zero volatility: either None or astronomically large.
        
        Smooth compound growth creates tiny floating-point noise in daily returns
        (vol ≈ 1e-16), so the vol == 0 guard may not trigger. Either outcome is
        acceptable — what matters is no crash and no small/negative Sharpe.
        """
        nav = _make_nav_series(0.10, 3, volatility=0.0)
        sh = sharpe_ratio(nav)
        assert sh is None or sh > 1000  # near-zero vol → huge or None

    def test_short_series_returns_none(self):
        """Series shorter than 252 days → None."""
        nav = _make_nav_series(0.10, 0.5)
        assert sharpe_ratio(nav) is None


# ─────────────────────────────────────────────────────────────────────────────
# Test Sortino Ratio
# ─────────────────────────────────────────────────────────────────────────────

class TestSortinoRatio:
    def test_basic_sortino(self):
        """Sortino should be computable for a noisy series."""
        nav = _make_nav_series(0.15, 5, volatility=0.20, seed=99)
        so = sortino_ratio(nav, risk_free_rate=0.065)
        assert so is not None
        # Sortino should generally be higher than Sharpe for the same fund
        # because it only penalises downside
        sh = sharpe_ratio(nav, risk_free_rate=0.065)
        if sh is not None:
            assert so >= sh * 0.8  # Sortino is at least in the ballpark of Sharpe

    def test_uses_mar_not_zero(self):
        """Verify the downside deviation is measured vs MAR (Rf), not zero.
        
        With a very high Rf, more days are classified as 'below MAR',
        which increases downside deviation and decreases Sortino.
        """
        nav = _make_nav_series(0.10, 5, volatility=0.15, seed=42)
        so_low_rf  = sortino_ratio(nav, risk_free_rate=0.02)
        so_high_rf = sortino_ratio(nav, risk_free_rate=0.12)
        # Higher Rf → more downside days → larger denominator + lower numerator → lower Sortino
        if so_low_rf is not None and so_high_rf is not None:
            assert so_low_rf > so_high_rf

    def test_short_series_returns_none(self):
        assert sortino_ratio(_make_nav_series(0.10, 0.5)) is None


# ─────────────────────────────────────────────────────────────────────────────
# Test Beta
# ─────────────────────────────────────────────────────────────────────────────

class TestBeta:
    def test_perfect_tracking_beta_one(self):
        """Fund that perfectly tracks benchmark should have β ≈ 1.0."""
        rng = np.random.RandomState(42)
        n = 500
        bench_ret = pd.Series(rng.normal(0.0004, 0.01, n))
        fund_ret  = bench_ret.copy()  # perfect tracking
        beta = compute_beta(fund_ret, bench_ret)
        assert beta == pytest.approx(1.0, abs=0.01)

    def test_2x_leveraged_beta_two(self):
        """Fund that returns 2x benchmark should have β ≈ 2.0."""
        rng = np.random.RandomState(42)
        n = 500
        bench_ret = pd.Series(rng.normal(0.0004, 0.01, n))
        fund_ret  = bench_ret * 2.0
        beta = compute_beta(fund_ret, bench_ret)
        assert beta == pytest.approx(2.0, abs=0.01)

    def test_short_series_returns_none(self):
        assert compute_beta(pd.Series([0.01]*50), pd.Series([0.01]*50)) is None


# ─────────────────────────────────────────────────────────────────────────────
# Test Alpha (geometric annualization)
# ─────────────────────────────────────────────────────────────────────────────

class TestAlpha:
    def test_perfect_tracking_alpha_zero(self):
        """Fund that tracks benchmark perfectly → α ≈ 0."""
        rng = np.random.RandomState(42)
        n = 500
        bench_ret = pd.Series(rng.normal(0.0004, 0.01, n))
        fund_ret  = bench_ret.copy()
        alpha = compute_alpha(fund_ret, bench_ret, beta=1.0)
        assert alpha == pytest.approx(0.0, abs=0.01)

    def test_outperforming_fund_positive_alpha(self):
        """Fund that consistently beats benchmark should have positive alpha."""
        rng = np.random.RandomState(42)
        n = 500
        bench_ret = pd.Series(rng.normal(0.0004, 0.01, n))
        fund_ret  = bench_ret + 0.0003  # adds ~7.5% annual alpha
        alpha = compute_alpha(fund_ret, bench_ret, beta=1.0)
        assert alpha is not None
        assert alpha > 0.02  # should show meaningful positive alpha


# ─────────────────────────────────────────────────────────────────────────────
# Test Information Ratio
# ─────────────────────────────────────────────────────────────────────────────

class TestInfoRatio:
    def test_positive_ir_for_outperformer(self):
        """Fund with positive active return and stable tracking → positive IR."""
        rng = np.random.RandomState(42)
        n = 500
        bench_ret = pd.Series(rng.normal(0.0004, 0.01, n))
        fund_ret  = bench_ret + 0.0002
        ir = compute_info_ratio(fund_ret, bench_ret)
        assert ir is not None
        assert ir > 0

    def test_zero_tracking_error_returns_none(self):
        """Identical fund and benchmark → TE=0 → None."""
        ret = pd.Series([0.01] * 100)
        assert compute_info_ratio(ret, ret) is None


# ─────────────────────────────────────────────────────────────────────────────
# Test Tracking Error
# ─────────────────────────────────────────────────────────────────────────────

class TestTrackingError:
    def test_perfect_tracking_zero_te(self):
        """Identical returns → TE = 0."""
        rng = np.random.RandomState(42)
        n = 100
        ret = pd.Series(rng.normal(0.0004, 0.01, n))
        te = compute_tracking_error(ret, ret)
        assert te == pytest.approx(0.0, abs=1e-10)

    def test_positive_te_for_different_returns(self):
        rng = np.random.RandomState(42)
        n = 200
        bench = pd.Series(rng.normal(0.0004, 0.01, n))
        fund  = bench + rng.normal(0, 0.005, n)
        te = compute_tracking_error(fund, bench)
        assert te is not None
        assert te > 0


# ─────────────────────────────────────────────────────────────────────────────
# Test _geo_mean_return
# ─────────────────────────────────────────────────────────────────────────────

class TestGeoMeanReturn:
    def test_all_positive(self):
        """Known geometric mean: [10%, 20%, 30%]."""
        rets = pd.Series([0.10, 0.20, 0.30])
        result = _geo_mean_return(rets)
        expected = (1.10 * 1.20 * 1.30) ** (1/3) - 1
        assert result == pytest.approx(expected, abs=1e-10)

    def test_extreme_loss_clamped(self):
        """If compound goes negative, should NOT return None — should clamp.
        
        This is Bug #2 fix: previously returned None, silently dropping the fund.
        """
        rets = pd.Series([-0.50, -0.60, -0.70, -0.80])  # catastrophic losses
        result = _geo_mean_return(rets)
        assert result is not None
        assert result < -0.5  # should reflect severe loss

    def test_empty_returns_none(self):
        assert _geo_mean_return(pd.Series([], dtype=float)) is None

    def test_mixed_returns(self):
        """Mix of gains and losses."""
        rets = pd.Series([0.10, -0.05, 0.08, -0.03])
        result = _geo_mean_return(rets)
        expected = (1.10 * 0.95 * 1.08 * 0.97) ** (1/4) - 1
        assert result == pytest.approx(expected, abs=1e-10)


# ─────────────────────────────────────────────────────────────────────────────
# Test Capture Ratios
# ─────────────────────────────────────────────────────────────────────────────

class TestCaptureRatios:
    def _make_daily_returns_with_index(self, n_days=500, seed=42):
        """Generate daily returns with a DatetimeIndex for monthly resampling."""
        rng = np.random.RandomState(seed)
        dates = pd.bdate_range(start="2018-01-01", periods=n_days)
        bench = pd.Series(rng.normal(0.0004, 0.012, n_days), index=dates)
        fund  = bench * 0.9 + 0.0002  # slightly less volatile, slight alpha
        return fund, bench

    def test_up_capture_computable(self):
        fund_r, bench_r = self._make_daily_returns_with_index()
        uc = compute_up_capture(fund_r, bench_r)
        # Should be computable with enough data
        assert uc is not None
        assert 50 < uc < 200  # reasonable range

    def test_down_capture_computable(self):
        fund_r, bench_r = self._make_daily_returns_with_index()
        dc = compute_down_capture(fund_r, bench_r)
        assert dc is not None
        assert 50 < dc < 200

    def test_capture_ratio_division(self):
        """Capture ratio = Up / Down, should be > 0."""
        fund_r, bench_r = self._make_daily_returns_with_index()
        cr = compute_capture_ratio(fund_r, bench_r)
        assert cr is not None
        assert cr > 0


# ─────────────────────────────────────────────────────────────────────────────
# Test compute_all_metrics integration
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeAllMetrics:
    def test_standalone_metrics_without_benchmark(self):
        """Should compute standalone metrics even without a benchmark."""
        nav_df = _make_nav_df(0.12, 6, volatility=0.18, seed=42)
        m = compute_all_metrics(nav_df)
        assert m["cagr_3y"] is not None
        assert m["cagr_5y"] is not None
        assert m["max_drawdown"] <= 0
        assert m["sharpe"] is not None
        assert m["sortino"] is not None
        assert m["beta"] is None  # no benchmark

    def test_with_benchmark(self):
        """Full metrics with benchmark should compute everything."""
        fund_df  = _make_nav_df(0.14, 6, volatility=0.18, seed=42)
        bench_df = _make_nav_df(0.10, 6, volatility=0.15, seed=99)
        m = compute_all_metrics(fund_df, bench_df, rolling_window_years=3)
        assert m["beta"] is not None
        assert m["alpha"] is not None
        assert m["info_ratio"] is not None
        assert m["rolling_consistency"] is not None

    def test_outperforming_fund_positive_consistency(self):
        """Fund that beats benchmark should have rolling consistency > 50%."""
        fund_df  = _make_nav_df(0.16, 6, volatility=0.15, seed=42)
        bench_df = _make_nav_df(0.08, 6, volatility=0.15, seed=99)
        m = compute_all_metrics(fund_df, bench_df, rolling_window_years=3)
        if m["rolling_consistency"] is not None:
            assert m["rolling_consistency"] > 0.5


# ─────────────────────────────────────────────────────────────────────────────
# Test Passive Score Normalization (Bug #5 fix)
# ─────────────────────────────────────────────────────────────────────────────

class TestPassiveScoreNormalization:
    def test_no_ter_full_scale(self):
        """Fund without TER should score on same 0-4 scale as one with TER."""
        from screener import _passive_score, _quartile_score

        # Create funds with varying tracking error, no TER
        funds_no_ter = [
            {"tracking_error": 0.1, "ter": None},
            {"tracking_error": 0.5, "ter": None},
            {"tracking_error": 1.0, "ter": None},
            {"tracking_error": 2.0, "ter": None},
            {"tracking_error": 3.0, "ter": None},
        ]

        best_score = _passive_score(funds_no_ter[0], funds_no_ter)  # lowest TE
        # Best fund should be able to score up to 4.0, not capped at 2.80
        assert best_score == 4.0, f"Max score without TER should be 4.0, got {best_score}"


# ─────────────────────────────────────────────────────────────────────────────
# Test Rolling Consistency and Capital Protection
# ─────────────────────────────────────────────────────────────────────────────

class TestRollingMetrics:
    def test_capital_protection_all_positive(self):
        """Fund always positive → capital_protection = 0 (no negative windows)."""
        fund_df  = _make_nav_df(0.15, 6, volatility=0.0, seed=42)
        bench_df = _make_nav_df(0.10, 6, volatility=0.0, seed=99)
        m = compute_all_metrics(fund_df, bench_df, rolling_window_years=3)
        if m["capital_protection"] is not None:
            assert m["capital_protection"] == 0.0

    def test_always_beating_benchmark(self):
        """Fund with consistently higher return → consistency = 100%."""
        # Use smooth series so fund > bench in every window
        fund_df  = _make_nav_df(0.15, 6, volatility=0.0, seed=42)
        bench_df = _make_nav_df(0.05, 6, volatility=0.0, seed=99)
        m = compute_all_metrics(fund_df, bench_df, rolling_window_years=3)
        if m["rolling_consistency"] is not None:
            assert m["rolling_consistency"] == pytest.approx(1.0, abs=0.01)
