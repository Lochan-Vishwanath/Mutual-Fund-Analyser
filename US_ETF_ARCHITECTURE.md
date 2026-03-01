# US ETF Analyzer Architecture (v1.1)

## Overview
This document outlines the architecture for a production-grade US Exchange Traded Fund (ETF) screening and backtesting engine. It builds upon a 5-phase relative-gating methodology adapted for the US ETF market, including liquidity mechanics, timezone NAV desyncs, "Smart Beta" index classification, and trading friction.

---

## 1. Data Layer & Caching (The Hybrid Model)
The system uses a highly cached hybrid data model to minimize API costs while maximizing data integrity.

### Data Sources
*   **Pricing & Yield (`yfinance` + FRED):** 
    *   Daily Adjusted Closes (`auto_adjust=True`) for Total Return (includes dividends/distributions).
    *   30-Day Trailing Dollar Volume (Close × Volume) for liquidity measurement.
    *   Expense Ratio (TER) via `.info['expenseRatio']`.
    *   Risk-Free Rate: 3-month US T-Bill yield from FRED.
*   **Metadata & Holdings (Financial Modeling Prep - Free Tier):**
    *   ETF Universe Classification (Morningstar Categories).
    *   Active/Passive designation.
    *   Top 10 Holdings + Concentration percentages.

### Outlier Rejection & Data Integrity
*   **Outlier Rejection:** A cleanup pass identifies any single-day return `> ±20%` (typically caused by bad split adjustments). These values are replaced with `0%` to prevent contamination of rolling metrics.
*   **Survivorship Bias Mitigation:** Uses a manual `graveyard.json` to inject liquidated ETFs into the backtest universe.
    *   **Schema for `graveyard.json`:**
        ```json
        {
          "DEAD_ETF_TICKER": {
            "name": "Some ETF That Closed",
            "category": "US Small Cap Active",
            "benchmark_ticker": "IWM",
            "inception_date": "2014-03-15",
            "delisted_date": "2021-08-20",
            "reason": "Liquidated — insufficient AUM",
            "final_aum_m": 45
          }
        }
        ```

### Cache TTL (Time-To-Live) Rules
To ensure data freshness while respecting API limits, the following TTL rules apply:
| Data Type | TTL Duration | Reason |
|---|---|---|
| Daily Pricing | 24 Hours | Captures previous day's close |
| Expense Ratio (TER) | 30 Days | Changes infrequently (annual/semi-annual) |
| AUM / Metadata | 30 Days | Monthly updates are sufficient |
| Portfolio Holdings | 90 Days | Quarterly reporting cycle (13F/N-PORT) |
| Risk-Free Rate | 7 Days | Weekly FRED sync |

---

## 2. Category Configuration Table
The engine operates across 6 core categories, each with specific benchmarks and constraints.

| Category | Strategy Fork | Benchmark | AUM Min | AUM Max | Rolling Window | Consistency Floor | Friction |
|---|---|---|---|---|---|---|---|
| US Large Blend | Passive | SPY | $500M | None | 3yr | 55% | 3bps |
| US Large Growth Active | Active | QQQ | $100M | None | 3yr | 55% | 3bps |
| US Small Cap Active | Active | IWM | $100M | $10B | 5yr | 55% | 8bps |
| International Developed | Passive | EFA | $100M | None | 3yr | 50% | 10bps |
| International EM | Active | EEM | $100M | None | 5yr | 50% | 15bps |
| US Bonds Intermediate | Passive | AGG | $100M | None | 3yr | 55% | 5bps |

*\*Note: US Bonds Intermediate has looser gate thresholds (Sharpe, Consistency) due to the lower volatility and structural nature of the asset class.*

---

## 3. The 5-Phase Analysis Pipeline

### Phase 0: Pre-Filtering & Classification
*   **Exclude Exotics:** Filter out Leveraged/Inverse ETFs (names containing "2x", "3x", "Ultra", "Short", "-X") and ETNs.
*   **Factor Classifier:**
    *   If `index_tracked` contains "Quality", "Momentum", "Value", "Dividend", "Fundamental", "Equal Weight" → **Standard Factor**.
    *   If `index_tracked` contains "Low Volatility", "Minimum Variance", "Defensive" → **Defensive Factor**.
    *   If `index_tracked` is a broad market cap index → **Passive**.
    *   **Fallback Rule:** If no keywords match, the ETF defaults to **Active / Standard Factor** scoring.
    *   **Overrides:** Every routing decision is written to a `CLASSIFICATION_LOG`. Edge cases can be manually forced via a `classification_overrides.json` file.

### Phase 1: Static Hard Gates
*   **History Gate:** 3-year minimum track record.
*   **AUM Gate:** See Category Configuration Table.
*   **Liquidity Gate:** 30-Day Trailing Dollar Volume must be `> $10M/day`.

### Phase 2: Hybrid Dynamic Gates (Category-Relative)
*   **Sharpe Ratio:** Must be `> 0` (vs T-Bill rate).
*   **Expense Ratio (TER) Gate:** 
    *   *Passive:* Must be within `0.05%` (5 bps) of the category median.
    *   *Active/Factor:* Must be `≤ Category Median + 0.30%`.
*   **Rolling Consistency:** Must beat the category benchmark in `> X%` of rolling windows (see Consistency Floor in table).
*   **Graceful Degradation:** If an ETF has fewer than 12 valid rolling windows for its primary window (e.g., 5yr), it falls back to 3yr windows with a `SHORT_HISTORY` flag and a `0.95x` score penalty.

### Phase 3: Multi-Dimensional Weighted Scoring
ETFs surviving the gates are ranked using quartile scoring across three forks:

#### A. Passive Strategy (Replication & Cost)
*   **55% Tracking Error:** Variance of the gap vs. Benchmark.
*   **25% Expense Ratio (TER):** Direct yield drag.
*   **20% Tracking Difference:** Mean of the gap vs. Benchmark.

#### B. Active / Standard Factor Strategy (Skill & Asymmetry)
*   **25% Information Ratio:** Alpha per unit of active tracking risk.
*   **22% Rolling Consistency:** % of rolling windows beating the benchmark.
*   **20% Capture Ratio:** Upside Capture ÷ Downside Capture.
*   **18% Sortino Ratio:** Return per unit of downside volatility.
*   **15% Alpha Stability:** Rolling standard deviation of Alpha.

> **Currency Beta Warning (International/EM):** For US-listed International ETFs, Information Ratio and Alpha calculations conflate stock-picking skill with USD/Foreign Currency fluctuations. This is a primary scoring risk for these categories.

#### C. Defensive Factor Strategy (Capital Preservation)
*   **25% Information Ratio**
*   **22% Rolling Consistency**
*   **20% Max Drawdown vs Benchmark**
*   **18% Sortino Ratio**
*   **15% Alpha Stability**

### Phase 4: Qualitative Red Flags
*   **Concentration Flag:** Top 10 holdings account for `> 50%` of total AUM.
*   **Premium/Discount Flag:** 30-day average premium/discount `> 0.5%`. (Disabled for International/EM to prevent false positives from Timezone NAV desync).
*   **Volatility Shift Flag:** Recent 24-month volatility deviates `> 1.5` SD from the prior 36-month volatility.
*   **High Beta Flag:** Beta `> 1.2` vs SPY.

---

## 4. Backtesting Engine & Trading Friction
The pipeline includes a historical simulator measuring forward returns net of trading costs.

*   **Category-Specific Friction Penalty:** Applied round-trip whenever a fund is swapped (see table).
*   **Continuity Rule:** The model proves the value of holding a #3 fund rather than incurring friction costs to switch to a new #2 fund.
*   **Point-in-Time Metadata Limitation:** The backtester uses current AUM, TER, and Holdings as proxies for historical data. Historical point-in-time metadata is not available in the current free-tier data model.

---

## 5. Known Limitations
*   **Backtest Survivorship:** While `graveyard.json` mitigates the bulk of bias, micro-ETFs that liquidated rapidly may still slip through, slightly inflating historical universe averages.
