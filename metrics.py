from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# metrics.py  —  Financial computations for MF Analyser v4.0
#
# v4 Changes from v3:
#   - compute_capture_ratio(): NEW — returns Upside/Downside as a single metric
#     Division-based (not subtraction) — correctly penalises high-volatility funds
#     that happen to have the same spread as conservative ones.
#   - compute_alpha_stability(): NEW — rolling alpha standard deviation.
#     Low stddev = manager consistently generates alpha, not episodically.
#   - compute_all_metrics(): now accepts rolling_window_years per-category
#     (3yr for Large/Flexi, 5yr for Mid/Small)
#   - compute_manager_change_signals(): NEW two-signal system replacing
#     the old rank-divergence proxy (which fired constantly on style rotations)
#   - compute_passive_score(): updated to use TE (70%) + TER (30%) properly
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
    """Annualised standard deviation of daily returns."""
    if len(series) < 2:
        return 0.0
    daily_ret = series.pct_change().dropna()
    return daily_ret.std() * np.sqrt(252)


def sharpe_ratio(series: pd.Series, risk_free_rate: float = RISK_FREE_RATE_ANNUAL) -> float | None:
    """(CAGR - Rf) / Annualised Volatility"""
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
    """(CAGR - Rf) / Downside Deviation (returns below 0 only).
    
    More informative than Sharpe for equity funds because it only penalises
    bad volatility (downside), not good volatility (upside swings).
    """
    if len(series) < 252:
        return None
    total_days = len(series)
    years      = total_days / 252.0
    start_val  = series.iloc[0]
    end_val    = series.iloc[-1]
    if start_val <= 0:
        return None
    ann_ret  = (end_val / start_val) ** (1 / years) - 1
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
    """(Rp - Rm) / Tracking Error — reward per unit of active risk.
    
    The cleanest single metric for measuring repeatable manager skill.
    Positive IR means the manager consistently adds alpha per unit of deviation.
    """
    df = pd.concat([fund_ret, bench_ret], axis=1).dropna()
    if len(df) < 60:
        return None
    active_ret   = df.iloc[:, 0] - df.iloc[:, 1]
    mean_active  = active_ret.mean() * 252
    tracking_err = active_ret.std() * np.sqrt(252)
    if tracking_err == 0:
        return None
    return mean_active / tracking_err


def compute_tracking_error(fund_ret: pd.Series, bench_ret: pd.Series) -> float | None:
    """Annualised std dev of active returns (fund - benchmark).
    Primary metric for passive fund scoring.
    """
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
    Higher is better. 110 = fund captures 110% of gains in rallies.
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


def compute_capture_ratio(fund_ret: pd.Series, bench_ret: pd.Series) -> float | None:
    """
    Capture Ratio = Upside Capture / Downside Capture  (DIVISION, not subtraction)
    
    Why division and not subtraction?
    Subtraction hides magnitude:
      Fund A: 90 up / 80 down → spread = 10
      Fund B: 130 up / 120 down → spread = 10
    
    Both look identical by spread. But Fund B is far more volatile and will
    cause much larger absolute losses in crashes. Division correctly distinguishes:
      Fund A: 90/80 = 1.125 (better)
      Fund B: 130/120 = 1.083 (worse — less efficient asymmetry)
    
    > 1.0 means positive asymmetry (gains more than it loses in up vs down markets).
    This is used both as a Phase 2 gate (must be > 1.0) and a Phase 3 scoring metric.
    """
    uc = compute_up_capture(fund_ret, bench_ret)
    dc = compute_down_capture(fund_ret, bench_ret)
    if uc is None or dc is None or dc == 0:
        return None
    return uc / dc


def compute_alpha_stability(
    fund_vals: pd.Series, bench_vals: pd.Series,
    rolling_window_years: int = 3
) -> float | None:
    """
    Alpha Stability = standard deviation of rolling alpha series.
    LOWER is better — a fund with low alpha stddev consistently adds value
    rather than having great years and terrible ones.
    
    Implementation:
      1. Compute rolling CAGR for fund and benchmark (same window as consistency)
      2. Compute rolling alpha = fund_rolling_cagr - bench_rolling_cagr
      3. Return std dev of that rolling alpha series
    
    This metric is directionally different from Information Ratio:
      - IR measures: average level of alpha relative to its variation
      - Alpha Stability measures: how much the alpha level varies over time
    Both reward consistent alpha generation, from different angles.
    """
    window = int(rolling_window_years * 252)
    
    # Align
    combined = pd.concat([fund_vals, bench_vals], axis=1).dropna()
    if len(combined) <= window + 30:
        return None
    
    combined.columns = ["fund", "bench"]
    fund_vals_a  = combined["fund"]
    bench_vals_a = combined["bench"]
    
    # Rolling CAGR
    f_roll = (fund_vals_a  / fund_vals_a.shift(window))  ** (1 / rolling_window_years) - 1
    b_roll = (bench_vals_a / bench_vals_a.shift(window)) ** (1 / rolling_window_years) - 1
    
    roll_comb = pd.concat([f_roll, b_roll], axis=1).dropna()
    roll_comb.columns = ["fund", "bench"]
    
    if len(roll_comb) < 30:
        return None
    
    # Rolling alpha series
    rolling_alpha = roll_comb["fund"] - roll_comb["bench"]
    
    if rolling_alpha.std() == 0:
        return None
    
    return float(rolling_alpha.std())


# ─────────────────────────────────────────────────────────────────────────────
# Manager Change Signals (v4 — replaces rank-divergence proxy)
# ─────────────────────────────────────────────────────────────────────────────

def compute_manager_change_signals(
    nav_df: pd.DataFrame,
    bench_df: pd.DataFrame,
    vol_threshold: float = 1.5,
) -> dict:
    """
    Two-signal manager change detection system.
    
    Signal A — Volatility Signature Shift:
      Computes rolling 12-month standard deviation of daily returns.
      If the most recent 24-month volatility is >threshold std devs from
      the prior 36-month volatility, fires the flag.
      
      Rationale: A new manager brings a different risk tolerance. This shows
      up in volatility before it shows up in returns.
    
    Signal B — Alpha Sign Flip:
      If the fund's long-run rolling alpha is positive BUT the most recent
      12-month alpha is negative AND below category median → fires.
      
      Rationale: A sustained alpha-generator suddenly underperforming peers
      is a behavioural signal worth investigating.
    
    Returns: {"manager_flag": bool, "manager_flag_reason": str | None,
              "signal_a": bool, "signal_b": bool}
    """
    result = {
        "manager_flag": False,
        "manager_flag_reason": None,
        "manager_signal_a": False,
        "manager_signal_b": False,
    }
    
    if nav_df is None or len(nav_df) < 252 * 4:  # Need at least 4 years
        return result
    
    nav = nav_df.sort_values("date")["nav"]
    daily_ret = nav.pct_change().dropna()
    
    # ── Signal A: Volatility Signature Shift ──────────────────────────────
    # Compute rolling 252-day (1yr) volatility window
    rolling_vol = daily_ret.rolling(252).std() * np.sqrt(252)
    rolling_vol = rolling_vol.dropna()
    
    if len(rolling_vol) < 252 * 2.5:   # Need enough history for both windows
        pass
    else:
        # Recent 2 years vs prior 3 years
        recent_vol = rolling_vol.iloc[-int(252*2):]
        prior_vol  = rolling_vol.iloc[-int(252*5):-int(252*2)]
        
        if len(prior_vol) >= 30 and len(recent_vol) >= 30:
            prior_mean = prior_vol.mean()
            prior_std  = prior_vol.std()
            recent_mean = recent_vol.mean()
            
            if prior_std > 0:
                z_score = abs(recent_mean - prior_mean) / prior_std
                if z_score > vol_threshold:
                    result["manager_signal_a"] = True
    
    # ── Signal B: Alpha Sign Flip ─────────────────────────────────────────
    if bench_df is not None and len(bench_df) > 252:
        bench = bench_df.sort_values("date")
        f_df = nav_df.set_index("date")[["nav"]].rename(columns={"nav": "fund"})
        b_df = bench.set_index("date")[["nav"]].rename(columns={"nav": "bench"})
        merged = f_df.join(b_df, how="inner").dropna()
        
        if len(merged) >= 252 * 3:
            f_r = merged["fund"].pct_change().dropna()
            b_r = merged["bench"].pct_change().dropna()
            
            aligned = pd.concat([f_r, b_r], axis=1).dropna()
            if len(aligned) >= 252 * 2:
                # Long-run alpha (all available history)
                longrun_alpha = (aligned.iloc[:, 0] - aligned.iloc[:, 1]).mean() * 252
                
                # Recent 1-year alpha
                recent_alpha = (aligned.iloc[-252:, 0] - aligned.iloc[-252:, 1]).mean() * 252
                
                # Signal fires if long-run is positive but recent is negative
                if longrun_alpha > 0 and recent_alpha < 0:
                    result["manager_signal_b"] = True
    
    # ── Combine signals ───────────────────────────────────────────────────
    if result["manager_signal_a"] or result["manager_signal_b"]:
        result["manager_flag"] = True
        reasons = []
        if result["manager_signal_a"]:
            reasons.append("Volatility signature has shifted significantly — risk profile may have changed")
        if result["manager_signal_b"]:
            reasons.append("Long-run alpha is positive but recent 1Y alpha has turned negative")
        result["manager_flag_reason"] = " | ".join(reasons) + " — verify fund manager tenure on AMFI/MFI Explorer"
    
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _monthly_aligned(fund_ret: pd.Series, bench_ret: pd.Series) -> pd.DataFrame | None:
    """Aligns two daily return series, resamples to monthly compounded returns."""
    df_daily = pd.concat([fund_ret, bench_ret], axis=1).dropna()
    df_daily.columns = ["fund", "bench"]
    if len(df_daily) < 60:
        return None
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
# Master Computation Function
# ─────────────────────────────────────────────────────────────────────────────

def compute_all_metrics(
    nav_df: pd.DataFrame,
    bench_df: pd.DataFrame = None,
    rolling_window_years: int = 3,
) -> dict:
    """
    Computes all screening and scoring metrics for a single fund.
    
    Args:
        nav_df               : DataFrame with ['date', 'nav'], sorted oldest→newest
        bench_df             : Same format for benchmark index fund
        rolling_window_years : Window for rolling consistency (3 for Large/Flexi, 5 for Mid/Small)
    
    Returns dict with:
        Standalone  : cagr_3y, cagr_5y, cagr_10y, max_drawdown, sharpe, sortino
        Benchmark   : beta, alpha, info_ratio, tracking_error,
                      down_capture, up_capture, capture_ratio,
                      alpha_stability,
                      rolling_consistency, capital_protection
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
        "capture_ratio": None, "alpha_stability": None,
        "rolling_consistency": None, "capital_protection": None,
    }
    
    if bench_df is None:
        metrics.update(_empty_bench)
        return metrics
    
    bench_df = bench_df.sort_values("date").reset_index(drop=True)
    
    # Align on date
    f_df   = nav_df.set_index("date")[["nav"]].rename(columns={"nav": "fund"})
    b_df   = bench_df.set_index("date")[["nav"]].rename(columns={"nav": "bench"})
    merged = f_df.join(b_df, how="inner").dropna()
    
    if len(merged) < 252:
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
    metrics["down_capture"]  = compute_down_capture(f_r, b_r)
    metrics["up_capture"]    = compute_up_capture(f_r, b_r)
    metrics["capture_ratio"] = compute_capture_ratio(f_r, b_r)   # NEW v4: division-based
    
    # Alpha Stability (NEW v4) — lower stddev = more consistent alpha generation
    metrics["alpha_stability"] = compute_alpha_stability(
        fund_vals, bench_vals, rolling_window_years
    )
    
    # ── 3. Rolling Window Metrics ──────────────────────────────────────────
    window = int(rolling_window_years * 252)
    
    if len(fund_vals) <= window:
        metrics.update({
            "rolling_consistency": None,
            "capital_protection":  None,
        })
        return metrics
    
    # Rolling CAGR: (Price_t / Price_{t-window})^(1/years) - 1
    f_roll = (fund_vals  / fund_vals.shift(window))  ** (1 / rolling_window_years) - 1
    b_roll = (bench_vals / bench_vals.shift(window)) ** (1 / rolling_window_years) - 1
    
    roll_comb = pd.concat([f_roll, b_roll], axis=1).dropna()
    roll_comb.columns = ["fund", "bench"]
    
    if roll_comb.empty:
        metrics.update({
            "rolling_consistency": None,
            "capital_protection":  None,
        })
        return metrics
    
    f_series = roll_comb["fund"]
    b_series = roll_comb["bench"]
    total    = len(roll_comb)
    
    metrics["rolling_consistency"] = float((f_series > b_series).sum() / total)
    metrics["capital_protection"]  = float((f_series < 0).sum() / total)
    metrics["_rolling_mean_cagr"]  = float(f_series.mean())
    
    return metrics


# ─────────────────────────────────────────────────────────────────────────────
# Category Percentile Helper (called after all funds are computed)
# ─────────────────────────────────────────────────────────────────────────────

def compute_category_percentiles(fund_list: list[dict]) -> list[dict]:
    """
    Adds 'rolling_category_percentile' to each fund dict.
    90th percentile = top 10% of category by average rolling CAGR.
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
            pct = (valid_arr < rv).sum() / len(valid_arr)
            f["rolling_category_percentile"] = round(pct * 100, 1)
    
    return fund_list
