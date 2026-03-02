# Future Features — MF Analyser v5.0 Roadmap

> Detailed implementation plans for features identified in the Portfolio Alignment Report.
> These are features the tool currently **lacks** that the Portfolio Replan 2026 needs.

---

## 1. SWP Sustainability Score

### Problem
The tool ranks funds for **buying** (accumulation phase). But your plan's endgame is a ₹55,000/month **SWP withdrawal** from the equity corpus starting September 2033. A great "buy" fund is not always a great "withdraw from" fund.

### What to Measure
| Metric | Formula | Why It Matters for SWP |
|---|---|---|
| **Recovery Speed** | Median days to recover from >10% drawdowns | Fast recovery = fewer months you sell units at a loss |
| **NAV Stability** | Std deviation of monthly NAV returns | Smoother NAV = more predictable SWP income |
| **Drawdown Depth** | Average of worst 5% rolling drawdowns | Shallower crashes = less principal erosion during SWP |
| **SWP Survival Rate** | % of historical 5-year windows where a 5% SWR never depletes >30% of corpus | Direct simulation of "can this fund sustain monthly withdrawals?" |

### Implementation Plan

#### New file: `swp_metrics.py`

```python
def compute_recovery_speed(nav_series, threshold=0.10):
    """
    For every drawdown > threshold, compute days to recover to previous peak.
    Return median recovery days.
    """
    # Identify drawdown periods using peak-to-trough logic
    # For each trough, scan forward until NAV exceeds the previous peak
    # Return median of all recovery durations

def compute_nav_stability(nav_series):
    """
    Standard deviation of monthly returns (not daily — monthly is what
    SWP investors experience since they withdraw monthly).
    """
    # Resample to monthly, compute pct_change, return std * sqrt(12)

def compute_swp_survival(nav_series, withdrawal_rate=0.05, window_years=5):
    """
    Simulate rolling SWP: start with ₹100, withdraw withdrawal_rate/12 monthly.
    For each rolling window, check if corpus ever drops below 70% of starting value.
    Return % of windows where it doesn't.
    """
    # Rolling window simulation
    # Monthly: corpus = corpus * (1 + monthly_return) - monthly_withdrawal
    # Track if corpus falls below 70% threshold

def compute_swp_score(nav_series):
    """
    Weighted composite:
      Recovery Speed (30%) + NAV Stability (25%)
      + Drawdown Depth (25%) + SWP Survival (20%)
    """
```

#### Integration with screener.py
- Add `swp_score` to the fund dict after Phase 3 scoring
- Display as a separate column in the UI (not part of the ranking score)
- Useful for the user's Phase 3 (2030-2033) when selecting which fund to start SWP from

#### Estimated effort: 2-3 hours

---

## 2. Tax-Efficiency Layer

### Problem
Your plan uses a **dual-name strategy** (your name + mother's name) with annual LTCG harvesting. The tool doesn't consider tax impact when ranking funds.

### What to Measure
| Metric | Source | Impact |
|---|---|---|
| **Portfolio Turnover Ratio (PTR)** | AMFI factsheets (monthly) | High PTR = more frequent sell/buy by fund manager = more STCG events passed to unitholders via NAV |
| **Dividend History** | Fund factsheets | Dividend-paying funds are tax-inefficient under new regime (taxed at slab rate) |
| **Tax Drag Estimate** | Computed from PTR + holding period | Estimated annual tax leakage as % of returns |

### Implementation Plan

#### New file: `tax_metrics.py`

```python
def estimate_tax_drag(ptr_pct, holding_period_months, tax_slab=0.125):
    """
    Estimate the annual tax drag caused by fund manager's trading activity.
    
    Approximate model:
      - PTR of X% means X% of portfolio is sold and rebought per year
      - Gains on the sold portion: estimated as (CAGR * sold_pct)
      - If held < 12 months: STCG at 20%, else LTCG at 12.5%
      - Tax drag = tax_rate * estimated_realised_gains
    """

def compute_tax_efficiency_score(fund_dict):
    """
    Returns a tax efficiency score 1-4:
      4 = Growth-only, low PTR, no dividends (most tax-efficient)
      3 = Growth-only, moderate PTR
      2 = Growth-only, high PTR
      1 = Dividend-paying or very high PTR
    """
```

#### Data source challenge
PTR data is **not available via mfapi.in**. Options:
1. **Web scrape AMFI factsheets** — monthly PDFs, complex parsing
2. **Manual entry** — user maintains a `tax_overrides.json` with PTR for monitored funds
3. **Proxy from NAV volatility** — higher NAV autocorrelation can approximate lower turnover

#### Recommended approach: Start with option 2 (manual JSON), upgrade to option 1 later.

#### Integration
- Add `tax_efficiency` as a Phase 4 **flag** (not a scoring metric)
- Flag funds with PTR > 100% as "⚠️ HIGH TURNOVER — tax drag risk"
- In the UI, show estimated annual tax drag as a tooltip

#### Estimated effort: 3-4 hours (option 2), 8-10 hours (option 1 with PDF parsing)

---

## 3. Cash Tent Category (Arbitrage + Liquid Fund Scoring)

### Problem
Your plan introduces ₹30K/month Arbitrage + ₹20K/month Liquid fund SIPs in Phase 3 (June 2030). The tool has no category for defensive/income funds. These funds need completely different scoring criteria — stability over returns.

### What to Measure
| Metric | Weight | Why |
|---|---|---|
| **Yield Consistency** | 40% | Monthly/quarterly yields should be stable (low stddev) |
| **Expense Ratio (TER)** | 30% | At 6-7% returns, every 0.1% TER matters enormously |
| **Liquidity (T+)** | 20% | Liquid = T+1, Arbitrage = T+2. Score based on redemption speed |
| **AUM Size** | 10% | Larger AUM = more stable in stress scenarios |

### Implementation Plan

#### Config changes: `config.py`

```python
# New category entries
CATEGORIES["Arbitrage"] = {
    "strategy":               "defensive",
    "amfi_category_keywords": ["Arbitrage Fund"],
    "name_must_contain":      [],
    "benchmark_code":         None,  # No benchmark — absolute return category
    "aum_min":                5000,  # Large AUM is critical for arbitrage
    "aum_max":                None,
    "min_history_years":      3,
    "rolling_window_years":   1,    # Short window — stability visible in 1 year
    "consistency_floor_key":  None,
}

CATEGORIES["Liquid"] = {
    "strategy":               "defensive",
    "amfi_category_keywords": ["Liquid Fund"],
    "name_must_contain":      [],
    "benchmark_code":         None,
    "aum_min":                10000,  # Only large, stable liquid funds
    "aum_max":                None,
    "min_history_years":      3,
    "rolling_window_years":   1,
    "consistency_floor_key":  None,
}

DEFENSIVE_SCORE_WEIGHTS = {
    "yield_consistency": 0.40,
    "ter":               0.30,
    "liquidity":         0.20,
    "aum_stability":     0.10,
}
```

#### New scoring path in `screener.py`

```python
def _defensive_score(fund: dict, all_funds: list) -> float:
    """
    Phase D scoring for Arbitrage/Liquid funds.
    Stability > Returns. Lower volatility = higher score.
    """
    # yield_consistency: inverse of monthly return stddev
    # ter: lower is better
    # liquidity: T+1 = 4.0, T+2 = 3.0, T+3 = 2.0
    # aum_stability: quartile scoring on AUM
```

#### Integration
- Add `"defensive"` as a third strategy alongside `"active"` and `"passive"`
- Skip Phase 2 gates entirely (no benchmark, no Sharpe gate, no RC)
- Phase 3 uses `DEFENSIVE_SCORE_WEIGHTS`
- Phase 4 flags: only Beta flag (should be near 0) and TER outlier detection

#### Timeline alignment
- This feature is needed by **June 2030** — not urgent
- Recommended to build 3-6 months before Phase 3 starts (late 2029)

#### Estimated effort: 4-5 hours

---

## Priority and Timeline

| Feature | Priority | When Needed | Effort | Dependency |
|---|---|---|---|---|
| **Phase 3 Rebalance** | ✅ Done | Now | — | — |
| **Phase 2 RC Floor** | ✅ Done | Now | — | — |
| **Phase 4 Signal B** | ✅ Done | Now | — | — |
| **SWP Sustainability** | 🟡 Medium | By 2032 (pre-SWP setup) | 2-3 hours | None |
| **Tax Efficiency** | 🟡 Medium | By April 2026 (LTCG harvest) | 3-4 hours | PTR data source |
| **Cash Tent Category** | 🟢 Low | By late 2029 (pre-Phase 3) | 4-5 hours | None |
