# 📈 MF Master Plan: The Unified Fund Selection Strategy (v3) 🇮🇳

**The definitive automated screening system for Indian Mutual Funds.**  
*Built for consistency, engineered for risk protection, and designed to kill the wealth-destroying cycle of serial switching.*

---

## 🏛 Foundational Philosophy

Two things kill retail investor returns more than bad fund selection:
1.  **Switching Costs**: Chasing the current rank-1 fund creates exit loads, capital gains tax, and disrupted compounding.
2.  **Trailing Return Illusion**: Selecting funds based on distorted base periods (like post-Covid recoveries) gives a false sense of alpha.

This tool implements a **Unified Strategy** (v3) that combines:
- **Benchmark Floor**: Ensures the fund beats a passive index consistently
- **Dynamic Category Gates**: Adapts to market regimes (bear/bull) automatically
- **Hybrid Scoring**: Combines risk-adjusted metrics with relative peer comparison

---

## ⚔️ Key Features

### 1. Large Cap "Winner's Circle" (Active vs Passive)
Over any 10-year window, ~85% of active large-cap funds underperform the Nifty 50 TRI.
- The UI provides a **side-by-side comparison** of top-tier Active Managers vs low-cost Index Funds.
- **Active Funds** are scored on Rolling Consistency, Sortino, and Capture Ratios.
- **Passive Funds** are ranked purely by **Tracking Error** and **Expense Ratio**.

### 2. The Continuity Rule (Holdover vs. New Entrant) 🛡️
The system remembers previous results to prevent "serial switching."
- **Holdover 🛡️**: Fund was in the Top 3 last quarter. If it's still performing, **leave it alone**.
- **New Entrant 🌟**: Fund is new to the Top 3. Requires the **Manual Checklist** before capital is moved.

### 3. Hybrid Dynamic Gates (The v3 Innovation)
Unlike traditional screeners that use static thresholds (e.g., "must have 12% returns"), this tool uses **Dynamic Gates** that adapt to market conditions:
- **Benchmark Floor**: Hard floor - fund must beat the index >50% of the time (keeps managers honest)
- **Category Median**: Dynamic - fund must be better than half its peers
- **Category Average**: Dynamic - capture ratios are compared to peer average

This prevents false "sell" signals in bear markets while still eliminating poor managers.

---

## 🧠 The Screening Strategy (v3)

### Phase 1: Hard Filters (Static)
| Gate | Threshold | Rationale |
| :--- | :--- | :--- |
| **History** | ≥ 5-7 Years | Guarantees the fund has survived at least one full market cycle. |
| **AUM Bounds** | ₹500Cr - ₹50kCr | Prevents liquidity risk (too small) or mandate drift (too large). |

### Phase 2: Hybrid Dynamic Gates (The Innovation)
A fund must pass **BOTH** the Benchmark Floor AND the Category Gate:

| Metric | Benchmark Floor | Category Gate | Rationale |
| :--- | :--- | :--- | :--- |
| **Rolling Consistency** | ≥ 50% | > Category Median | Must beat index consistently AND be better than peers. |
| **Upside Capture** | — | > Category Average | Must participate in rallies better than average peers. |
| **Downside Capture** | — | < Category Average | Must protect better than average peers. |
| **Negative Sharpe** | > 0 | — | Hard filter: no negative risk-adjusted returns. |

*Note: Absolute Return (12% CAGR) gate has been removed to prevent false exits during bear markets.*

### Phase 3: Multi-Dimensional Weighted Scoring
Qualified survivors are ranked using a 1-4 quartile scale across seven dimensions:

| Metric | Weight | Why it matters |
| :--- | :--- | :--- |
| **Rolling Consistency** | 18% | Genuine consistency vs. lucky trailing returns. |
| **Sortino Ratio** | 20% | Return per unit of *downside* risk (preferred over Sharpe). |
| **Upside Capture** | 18% | Participation in bull markets (don't buy "expensive defensive" funds). |
| **Downside Capture** | 15% | Protection during market crashes. |
| **Information Ratio** | 15% | Manager skill: consistency of excess returns over benchmark. |
| **Max Drawdown** | 9% | Behavioral check: can you actually stomach the worst-case drop? |
| **Expense Ratio (TER)**| 5% | Low cost wins ties. |

---

## 📋 Phase 4: The Manual Verification (The Human Loop)

The tool performs 90% of the heavy lifting. You must manually verify these 5 points for the Top 3 funds before investing:

1.  **Fund Manager Tenure**: Is the person who built the track record still at the helm? (< 3y = risk).
2.  **Sector Concentration**: No single sector should exceed **35%** of the portfolio.
3.  **Stock Concentration**: Top-10 holdings should be **< 60%** (avoid high conviction single-stock risk).
4.  **Portfolio P/E**: Compare fund P/E vs benchmark. A gap **> 30%** indicates a heavy valuation bet.
5.  **SEBI Stress Test**: (Mid/Small Cap) Check "Days to liquidate 50% of portfolio." **> 30 days** is risky.

---

## 🚀 Getting Started

### 1. Setup Environment
```bash
# Clone and install
git clone https://github.com/YourUsername/Mutual-Fund-Analyser.git
cd Mutual-Fund-Analyser
pip install -r requirements.txt

# Setup credentials
cp .env.example .env
# Edit .env with your Gmail App Password and Recipient Emails
```

### 2. Run the Screener
```bash
# Dry run (preview results in console)
python main.py --dry

# Send email to subscribers
python main.py --auto
```

### 3. Backtesting (Historical Validation)
```bash
# Test how the screener would have performed with data as of a specific date
python backtest.py 2020-06-30
python backtest.py 2023-06-30
```

### 4. CLI Power Tools
- `python utils.py search "Parag Parikh"`: Find scheme codes for any fund.
- `python utils.py verify 122639`: Run a deep health check on a specific fund.

---

## 🤖 Automation (GitHub Actions)

The project includes a pre-configured workflow (`.github/workflows/quarterly.yml`) that runs on the **1st of every quarter** (Jan, Apr, Jul, Oct).

**To enable:**
1. Push code to a private GitHub repo.
2. Go to Settings > Secrets > Actions.
3. Add `MF_EMAIL_PASSWORD`, `EMAIL_SENDER`, and `SUBSCRIBERS`.

---

## 📂 Architecture Overview
- `main.py`: Orchestrator - runs screening and sends emails.
- `backtest.py`: Historical validation tool for testing the screener on past data.
- `screener.py`: The heart of the system. Implements Phase 2 (Hybrid Gates) and Phase 3 (Scoring).
- `metrics.py`: Financial engine (CAGR, Rolling, Sharpe, Sortino, Capture Ratios).
- `fetcher.py`: Data ingestion from AMFI (AUM/Categories) and `mfapi.in` (NAV history).
- `emailer.py`: Builds the "Winner's Circle" HTML reports.
- `config.py`: Central command for weights, thresholds, and benchmark codes.
- `utils.py`: CLI toolbox for searching codes and verifying benchmarks.

---

## 💰 Cost: ₹0 / Month
This system relies entirely on public AMFI data and the free `mfapi.in` service. No expensive data subscriptions required.

---

*For personal use only. Not financial advice. Consult a SEBI-registered advisor before investing.*
