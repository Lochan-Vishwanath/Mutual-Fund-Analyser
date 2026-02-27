# ─────────────────────────────────────────────────────────────────────────────
# metrics.py  —  Financial computations.
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
    
    # Simple approximation: look back N*252 days.
    lookback = int(years * 252)
    if len(series) <= lookback:
        return None
        
    start_val = series.iloc[-(lookback + 1)]
    end_val   = series.iloc[-1]
    
    if start_val == 0: return 0.0
    # Handle negative start value? NAV is usually positive.
    if start_val < 0: return None 
    
    return (end_val / start_val) ** (1 / years) - 1


def max_drawdown(series: pd.Series) -> float:
    """Max peak-to-trough decline (negative value)."""
    if len(series) < 2:
        return 0.0
    
    roll_max = series.cummax()
    drawdown = (series - roll_max) / roll_max
    return drawdown.min()


def std_dev_annual(series: pd.Series) -> float:
    """Annualized standard deviation of daily returns."""
    if len(series) < 2: return 0.0
    daily_ret = series.pct_change().dropna()
    return daily_ret.std() * np.sqrt(252)


def sharpe_ratio(series: pd.Series, risk_free_rate: float = RISK_FREE_RATE_ANNUAL) -> float | None:
    """(CAGR - Rf) / Annualized Volatility"""
    if len(series) < 252: return None  # Need at least a year
    
    # Annualized return over the WHOLE period available in 'series'
    total_days = len(series)
    years = total_days / 252.0
    
    start_val = series.iloc[0]
    end_val   = series.iloc[-1]
    
    if start_val <= 0: return 0.0
    
    ann_ret = (end_val / start_val) ** (1 / years) - 1
    vol     = std_dev_annual(series)
    
    if vol == 0: return 0.0
    return (ann_ret - risk_free_rate) / vol


def sortino_ratio(series: pd.Series, risk_free_rate: float = RISK_FREE_RATE_ANNUAL) -> float | None:
    """(CAGR - Rf) / Downside Deviation"""
    if len(series) < 252: return None
    
    total_days = len(series)
    years = total_days / 252.0
    
    start_val = series.iloc[0]
    end_val   = series.iloc[-1]
    
    if start_val <= 0: return 0.0
    ann_ret = (end_val / start_val) ** (1 / years) - 1
    
    daily_ret = series.pct_change().dropna()
    # Downside deviation relative to 0
    downside = daily_ret[daily_ret < 0]
    
    if len(downside) == 0: return 0.0
    
    downside_dev = downside.std() * np.sqrt(252)
    if downside_dev == 0: return 0.0
    
    return (ann_ret - risk_free_rate) / downside_dev


# ─────────────────────────────────────────────────────────────────────────────
# Advanced Metrics Helpers
# ─────────────────────────────────────────────────────────────────────────────

def compute_beta(fund_ret: pd.Series, bench_ret: pd.Series) -> float:
    """Slope of fund returns vs benchmark returns."""
    # Align dates
    df = pd.concat([fund_ret, bench_ret], axis=1).dropna()
    if len(df) < 30: return 1.0
    
    cov = df.iloc[:, 0].cov(df.iloc[:, 1])
    var = df.iloc[:, 1].var()
    
    if var == 0: return 1.0
    return cov / var


def compute_alpha(fund_ret: pd.Series, bench_ret: pd.Series, beta: float, risk_free_rate: float = RISK_FREE_RATE_ANNUAL) -> float:
    """Jensen's Alpha: Rp - [Rf + Beta * (Rm - Rf)]"""
    df = pd.concat([fund_ret, bench_ret], axis=1).dropna()
    if len(df) < 30: return 0.0
    
    rp = df.iloc[:, 0].mean() * 252
    rm = df.iloc[:, 1].mean() * 252
    
    return rp - (risk_free_rate + beta * (rm - risk_free_rate))


def compute_info_ratio(fund_ret: pd.Series, bench_ret: pd.Series) -> float:
    """(Rp - Rm) / Tracking Error"""
    df = pd.concat([fund_ret, bench_ret], axis=1).dropna()
    if len(df) < 30: return 0.0
    
    active_ret = df.iloc[:, 0] - df.iloc[:, 1]
    mean_active = active_ret.mean() * 252
    tracking_error = active_ret.std() * np.sqrt(252)
    
    if tracking_error == 0: return 0.0
    return mean_active / tracking_error


def compute_tracking_error(fund_ret: pd.Series, bench_ret: pd.Series) -> float:
    """Std dev of active returns."""
    df = pd.concat([fund_ret, bench_ret], axis=1).dropna()
    if len(df) < 30: return 0.0
    
    active_ret = df.iloc[:, 0] - df.iloc[:, 1]
    return active_ret.std() * np.sqrt(252)


def compute_down_capture(fund_ret: pd.Series, bench_ret: pd.Series) -> float:
    """
    (Avg Down Market Return of Fund / Avg Down Market Return of Benchmark) * 100
    Down Market = Periods where Benchmark return < 0
    """
    df = pd.concat([fund_ret, bench_ret], axis=1).dropna()
    df.columns = ["fund", "bench"]
    
    down_days = df[df["bench"] < 0]
    
    if len(down_days) < 10: return 100.0
    
    avg_fund = down_days["fund"].mean()
    avg_bench = down_days["bench"].mean()
    
    if avg_bench == 0: return 100.0
    return (avg_fund / avg_bench) * 100


# ─────────────────────────────────────────────────────────────────────────────
# Master Function
# ─────────────────────────────────────────────────────────────────────────────

def compute_all_metrics(nav_df: pd.DataFrame, bench_df: pd.DataFrame = None, rolling_window_years: int = 5) -> dict:
    """
    Computes all screening metrics.
    nav_df, bench_df columns: ["date", "nav"]
    """
    # Prepare Fund Data
    nav_df = nav_df.sort_values("date").reset_index(drop=True)
    nav_series = nav_df["nav"]
    
    # 1. Standalone Metrics
    metrics = {
        "cagr_3y":       cagr(nav_series, 3),
        "cagr_5y":       cagr(nav_series, 5),
        "cagr_10y":      cagr(nav_series, 10),
        "max_drawdown":  max_drawdown(nav_series),
        "sharpe":        sharpe_ratio(nav_series),
        "sortino":       sortino_ratio(nav_series),
    }
    
    # 2. Benchmark-dependent Metrics
    if bench_df is not None:
        bench_df = bench_df.sort_values("date").reset_index(drop=True)
        
        # Align data (join on date)
        # We need to set index to date for proper joining
        f_df = nav_df.set_index("date")[["nav"]].rename(columns={"nav": "fund"})
        b_df = bench_df.set_index("date")[["nav"]].rename(columns={"nav": "bench"})
        
        merged = f_df.join(b_df, how="inner").dropna()
        
        if len(merged) > 252:
            fund_vals = merged["fund"]
            bench_vals = merged["bench"]
            
            # Daily returns
            f_r = fund_vals.pct_change().dropna()
            b_r = bench_vals.pct_change().dropna()
            
            # Re-align returns
            rets = pd.concat([f_r, b_r], axis=1).dropna()
            f_r = rets.iloc[:, 0]
            b_r = rets.iloc[:, 1]
            
            # Beta, Alpha, IR
            beta = compute_beta(f_r, b_r)
            metrics["beta"]  = beta
            metrics["alpha"] = compute_alpha(f_r, b_r, beta)
            metrics["info_ratio"] = compute_info_ratio(f_r, b_r)
            metrics["tracking_error"] = compute_tracking_error(f_r, b_r) * 100
            metrics["down_capture"] = compute_down_capture(f_r, b_r)
            
            # Rolling Consistency & Absolute Return Distribution
            window = int(rolling_window_years * 252)
            
            if len(fund_vals) > window:
                # Rolling CAGR over 'rolling_window_years'
                # (Price_t / Price_t-n)^(1/years) - 1
                f_roll_cagr = (fund_vals / fund_vals.shift(window)) ** (1 / rolling_window_years) - 1
                b_roll_cagr = (bench_vals / bench_vals.shift(window)) ** (1 / rolling_window_years) - 1
                
                # Align
                roll_comb = pd.concat([f_roll_cagr, b_roll_cagr], axis=1).dropna()
                
                if not roll_comb.empty:
                    f_series = roll_comb.iloc[:, 0]
                    b_series = roll_comb.iloc[:, 1]
                    total = len(roll_comb)
                    
                    # 1. Relative Consistency (% of time beating benchmark)
                    wins = (f_series > b_series).sum()
                    metrics["rolling_consistency"] = wins / total
                    
                    # 2. Absolute Returns Distribution (Advisorkhoj method)
                    # % of time beating the target absolute return (e.g. 12%)
                    from config import ABSOLUTE_RETURN_TARGET
                    target_wins = (f_series >= ABSOLUTE_RETURN_TARGET).sum()
                    metrics["absolute_consistency"] = target_wins / total
                    
                    # 3. Capital Protection (% of time with negative returns)
                    negative_returns = (f_series < 0).sum()
                    metrics["capital_protection"] = negative_returns / total
                    
                else:
                    metrics["rolling_consistency"] = None
                    metrics["absolute_consistency"] = None
                    metrics["capital_protection"] = None
            else:
                metrics["rolling_consistency"] = None
                metrics["absolute_consistency"] = None
                metrics["capital_protection"] = None
        else:
             metrics.update({
                "beta": None, "alpha": None, "info_ratio": None, 
                "down_capture": None, "rolling_consistency": None, "tracking_error": None,
                "absolute_consistency": None, "capital_protection": None
            })
            
    else:
        metrics.update({
            "beta": None, "alpha": None, "info_ratio": None, 
            "down_capture": None, "rolling_consistency": None, "tracking_error": None,
            "absolute_consistency": None, "capital_protection": None
})
        
    return metrics
