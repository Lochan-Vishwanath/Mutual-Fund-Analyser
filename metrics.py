# ─────────────────────────────────────────────────────────────────────────────
# metrics.py  —  Financial computations.
#
# v3 Changes:
#   - Added compute_up_capture() — symmetric counterpart to down_capture
#   - compute_all_metrics() now returns up_capture
#   - Added category_percentile_rolling computation helper
#   - compute_down_capture / up_capture use monthly-resampled returns for stability
# ─────────────────────────────────────────────────────────────────────────────

import numpy as np
import pandas as pd
from config import RISK_FREE_RATE_ANNUAL


# ─────────────────────────────────────────────────────────────────────────────
# Basic Metrics
# ─────────────────────────────────────────────────────────────────────────────

def cagr(series: pd.Series, years: int) -> float | None:
    """Compound Annual Growth Rate over the last 'years'."""
    if len(series) < 2:
        return None

    lookback = int(years * 252)
    if len(series) <= lookback:
        return None

    start_val = series.iloc[-(lookback + 1)]
    end_val   = series.iloc[-1]

    if start_val <= 0:
        return None

    return (end_val / start_val) ** (1 / years) - 1


def max_drawdown(series: pd.Series) -> float:
    """Max peak-to-trough decline (negative value, e.g. -0.38 means -38%)."""
    if len(series) < 2:
        return 0.0
    roll_max = series.cummax()
    drawdown = (series - roll_max) / roll_max
    return drawdown.min()


def std_dev_annual(series: pd.Series) -> float:
    """Annualized standard deviation of daily returns."""
    if len(series) < 2:
        return 0.0
    daily_ret = series.pct_change().dropna()
    return daily_ret.std() * np.sqrt(252)


def sharpe_ratio(series: pd.Series, risk_free_rate: float = RISK_FREE_RATE_ANNUAL) -> float | None:
    """(CAGR - Rf) / Annualized Volatility"""
    if len(series) < 252:
        return None

    total_days = len(series)
    years      = total_days / 252.0
    start_val  = series.iloc[0]
    end_val    = series.iloc[-1]

    if start_val <= 0:
        return None

    ann_ret = (end_val / start_val) ** (1 / years) - 1
    vol     = std_dev_annual(series)

    if vol == 0:
        return None
    return (ann_ret - risk_free_rate) / vol


def sortino_ratio(series: pd.Series, risk_free_rate: float = RISK_FREE_RATE_ANNUAL) -> float | None:
    """(CAGR - Rf) / Downside Deviation (returns below 0)."""
    if len(series) < 252:
        return None

    total_days = len(series)
    years      = total_days / 252.0
    start_val  = series.iloc[0]
    end_val    = series.iloc[-1]

    if start_val <= 0:
        return None

    ann_ret   = (end_val / start_val) ** (1 / years) - 1
    daily_ret = series.pct_change().dropna()
    downside  = daily_ret[daily_ret < 0]

    if len(downside) < 10:
        return None

    downside_dev = downside.std() * np.sqrt(252)
    if downside_dev == 0:
        return None

    return (ann_ret - risk_free_rate) / downside_dev


# ─────────────────────────────────────────────────────────────────────────────
# Benchmark-dependent Metrics
# ─────────────────────────────────────────────────────────────────────────────

def compute_beta(fund_ret: pd.Series, bench_ret: pd.Series) -> float | None:
    """Slope of fund returns vs benchmark returns (market sensitivity)."""
    df = pd.concat([fund_ret, bench_ret], axis=1).dropna()
    if len(df) < 60:
        return None
    cov = df.iloc[:, 0].cov(df.iloc[:, 1])
    var = df.iloc[:, 1].var()
    if var == 0:
        return None
    return cov / var


def compute_alpha(fund_ret: pd.Series, bench_ret: pd.Series, beta: float,
                  risk_free_rate: float = RISK_FREE_RATE_ANNUAL) -> float | None:
    """Jensen's Alpha: Rp - [Rf + Beta * (Rm - Rf)]"""
    df = pd.concat([fund_ret, bench_ret], axis=1).dropna()
    if len(df) < 60:
        return None
    rp = df.iloc[:, 0].mean() * 252
    rm = df.iloc[:, 1].mean() * 252
    return rp - (risk_free_rate + beta * (rm - risk_free_rate))


def compute_info_ratio(fund_ret: pd.Series, bench_ret: pd.Series) -> float | None:
    """(Rp - Rm) / Tracking Error — reward per unit of active risk."""
    df = pd.concat([fund_ret, bench_ret], axis=1).dropna()
    if len(df) < 60:
        return None
    active_ret    = df.iloc[:, 0] - df.iloc[:, 1]
    mean_active   = active_ret.mean() * 252
    tracking_err  = active_ret.std() * np.sqrt(252)
    if tracking_err == 0:
        return None
    return mean_active / tracking_err


def compute_tracking_error(fund_ret: pd.Series, bench_ret: pd.Series) -> float | None:
    """Annualized std dev of active returns (fund - benchmark)."""
    df = pd.concat([fund_ret, bench_ret], axis=1).dropna()
    if len(df) < 30:
        return None
    active_ret = df.iloc[:, 0] - df.iloc[:, 1]
    return active_ret.std() * np.sqrt(252)


def compute_down_capture(fund_ret: pd.Series, bench_ret: pd.Series) -> float | None:
    """
    Downside Capture Ratio (monthly returns for stability):
      (Geometric mean of fund returns in DOWN months /
       Geometric mean of bench returns in DOWN months) * 100

    DOWN months = benchmark monthly return < 0.
    Lower is better. 80 = fund falls only 80% as much as benchmark in crashes.
    """
    # Resample to monthly for stability (daily noise creates false signals)
    df = _monthly_aligned(fund_ret, bench_ret)
    if df is None:
        return None

    down_months = df[df["bench"] < 0]
    if len(down_months) < 6:
        return None

    fund_geo  = _geo_mean_return(down_months["fund"])
    bench_geo = _geo_mean_return(down_months["bench"])

    if bench_geo == 0 or bench_geo is None:
        return None
    return (fund_geo / bench_geo) * 100


def compute_up_capture(fund_ret: pd.Series, bench_ret: pd.Series) -> float | None:
    """
    Upside Capture Ratio (monthly returns for stability):
      (Geometric mean of fund returns in UP months /
       Geometric mean of bench returns in UP months) * 100

    UP months = benchmark monthly return >= 0.
    Higher is better. 110 = fund captures 110% of benchmark gains in rallies.
    A fund with high up_capture AND low down_capture has true skill (asymmetric returns).
    """
    df = _monthly_aligned(fund_ret, bench_ret)
    if df is None:
        return None

    up_months = df[df["bench"] >= 0]
    if len(up_months) < 6:
        return None

    fund_geo  = _geo_mean_return(up_months["fund"])
    bench_geo = _geo_mean_return(up_months["bench"])

    if bench_geo == 0 or bench_geo is None:
        return None
    return (fund_geo / bench_geo) * 100


def _monthly_aligned(fund_ret: pd.Series, bench_ret: pd.Series) -> pd.DataFrame | None:
    """
    Aligns two daily return series, resamples to monthly compounded returns.
    Returns DataFrame with columns ['fund', 'bench'] or None if insufficient data.
    """
    df_daily = pd.concat([fund_ret, bench_ret], axis=1).dropna()
    df_daily.columns = ["fund", "bench"]

    if len(df_daily) < 60:
        return None

    # Compound daily returns into monthly returns: (1+r1)(1+r2)...-1
    df_daily.index = pd.to_datetime(df_daily.index)
    df_monthly = df_daily.resample("ME").apply(lambda x: (1 + x).prod() - 1)

    if len(df_monthly) < 12:
        return None

    return df_monthly


def _geo_mean_return(returns: pd.Series) -> float | None:
    """Geometric mean of return series. Handles edge cases."""
    if len(returns) == 0:
        return None
    compound = (1 + returns).prod()
    if compound <= 0:
        return None
    return compound ** (1 / len(returns)) - 1


# ─────────────────────────────────────────────────────────────────────────────
# Master Function
# ─────────────────────────────────────────────────────────────────────────────

def compute_all_metrics(nav_df: pd.DataFrame, bench_df: pd.DataFrame = None,
                         rolling_window_years: int = 3) -> dict:
    """
    Computes all screening and scoring metrics for a fund.

    Args:
        nav_df    : DataFrame with columns ['date', 'nav'], sorted oldest→newest
        bench_df  : same format for benchmark index fund
        rolling_window_years: window size for rolling return computation

    Returns dict with:
        Standalone: cagr_3y, cagr_5y, cagr_10y, max_drawdown, sharpe, sortino
        Benchmark-dependent: beta, alpha, info_ratio, tracking_error,
                             down_capture, up_capture,
                             rolling_consistency, absolute_consistency,
                             capital_protection
    """
    nav_df     = nav_df.sort_values("date").reset_index(drop=True)
    nav_series = nav_df["nav"]

    # ── 1. Standalone Metrics ──────────────────────────────────────────────
    metrics = {
        "cagr_3y":      cagr(nav_series, 3),
        "cagr_5y":      cagr(nav_series, 5),
        "cagr_10y":     cagr(nav_series, 10),
        "max_drawdown": max_drawdown(nav_series),
        "sharpe":       sharpe_ratio(nav_series),
        "sortino":      sortino_ratio(nav_series),
    }

    # ── 2. Benchmark-dependent Metrics ────────────────────────────────────
    _empty_bench = {
        "beta": None, "alpha": None, "info_ratio": None,
        "tracking_error": None, "down_capture": None, "up_capture": None,
        "rolling_consistency": None, 
        "capital_protection": None,
    }

    if bench_df is None:
        metrics.update(_empty_bench)
        return metrics

    bench_df = bench_df.sort_values("date").reset_index(drop=True)

    # Align on date
    f_df = nav_df.set_index("date")[["nav"]].rename(columns={"nav": "fund"})
    b_df = bench_df.set_index("date")[["nav"]].rename(columns={"nav": "bench"})
    merged = f_df.join(b_df, how="inner").dropna()

    if len(merged) < 252:  # Need at least 1 year of aligned data
        metrics.update(_empty_bench)
        return metrics

    fund_vals  = merged["fund"]
    bench_vals = merged["bench"]

    # Daily returns (aligned)
    f_r = fund_vals.pct_change().dropna()
    b_r = bench_vals.pct_change().dropna()
    rets = pd.concat([f_r, b_r], axis=1).dropna()
    f_r  = rets.iloc[:, 0]
    b_r  = rets.iloc[:, 1]

    # Beta, Alpha, IR, Tracking Error
    beta = compute_beta(f_r, b_r)
    metrics["beta"]           = beta
    metrics["alpha"]          = compute_alpha(f_r, b_r, beta if beta else 1.0) if beta else None
    metrics["info_ratio"]     = compute_info_ratio(f_r, b_r)
    metrics["tracking_error"] = (compute_tracking_error(f_r, b_r) or 0) * 100  # as %

    # Capture Ratios (monthly for stability)
    metrics["down_capture"] = compute_down_capture(f_r, b_r)
    metrics["up_capture"]   = compute_up_capture(f_r, b_r)  # NEW in v3

    # ── 3. Rolling Window Metrics ──────────────────────────────────────────
    window = int(rolling_window_years * 252)

    if len(fund_vals) <= window:
        metrics.update({
            "rolling_consistency": None,
            
            "capital_protection": None,
        })
        return metrics

    # Rolling CAGR: (Price_t / Price_{t-window})^(1/years) - 1
    f_roll = (fund_vals / fund_vals.shift(window)) ** (1 / rolling_window_years) - 1
    b_roll = (bench_vals / bench_vals.shift(window)) ** (1 / rolling_window_years) - 1

    roll_comb = pd.concat([f_roll, b_roll], axis=1).dropna()
    roll_comb.columns = ["fund", "bench"]

    if roll_comb.empty:
        metrics.update({
            "rolling_consistency": None,
            
            "capital_protection": None,
        })
        return metrics

    f_series = roll_comb["fund"]
    b_series = roll_comb["bench"]
    total    = len(roll_comb)

    
    # Relative Consistency: % of time beating benchmark
    metrics["rolling_consistency"] = (f_series > b_series).sum() / total

    # Capital Protection: % of time fund had NEGATIVE rolling CAGR
    metrics["capital_protection"] = (f_series < 0).sum() / total
    # Capital Protection: % of time fund had NEGATIVE rolling CAGR
    metrics["capital_protection"] = (f_series < 0).sum() / total

    # Store the rolling series mean for category percentile computation (caller uses this)
    metrics["_rolling_mean_cagr"] = float(f_series.mean())

    return metrics


# ─────────────────────────────────────────────────────────────────────────────
# Category Percentile (called after all funds are computed)
# ─────────────────────────────────────────────────────────────────────────────

def compute_category_percentiles(fund_list: list[dict]) -> list[dict]:
    """
    Given a list of fund metric dicts (after compute_all_metrics),
    adds 'rolling_category_percentile' to each dict:
      - Percentile rank of the fund's average rolling CAGR vs all category peers
      - 90th percentile = top 10% of the category
    """
    rolling_means = [f.get("_rolling_mean_cagr") for f in fund_list]
    valid_means   = [v for v in rolling_means if v is not None and not np.isnan(v)]

    if len(valid_means) < 3:
        for f in fund_list:
            f["rolling_category_percentile"] = None
        return fund_list

    valid_arr = np.array(valid_means)

    for f in fund_list:
        rv = f.get("_rolling_mean_cagr")
        if rv is None or np.isnan(rv):
            f["rolling_category_percentile"] = None
        else:
            # Percentile of this fund's rolling mean vs all category peers
            pct = (valid_arr < rv).sum() / len(valid_arr)
            f["rolling_category_percentile"] = round(pct * 100, 1)

    return fund_list
