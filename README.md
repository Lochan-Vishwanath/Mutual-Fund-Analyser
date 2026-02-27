# 📈 MF Master Plan: The Unified Fund Selection Strategy (v3) 🇮🇳

**The definitive automated screening system for Indian Mutual Funds.**  
*Built for consistency, engineered for risk protection, and designed to kill the wealth-destroying cycle of serial switching.*

---

## 🏛 Foundational Philosophy

Two things kill retail investor returns more than bad fund selection:
1.  **Switching Costs**: Chasing the current rank-1 fund creates exit loads, capital gains tax, and disrupted compounding.
2.  **Trailing Return Illusion**: Selecting funds based on distorted base periods (like post-Covid recoveries) gives a false sense of alpha.

This tool implements a **Unified Strategy** (v3) that combines absolute return distribution logic, a rigorous risk framework, and practical behavioral safeguards to find funds you can hold with confidence for 5+ years.

---

## ⚔️ Key Features

### 1. Large Cap "Winner's Circle" (Active vs Passive)
Over any 10-year window, ~85% of active large-cap funds underperform the Nifty 50 TRI.
- The UI provides a **side-by-side comparison** of top-tier Active Managers vs low-cost Index Funds.
- **Active Funds** are scored on Alpha, Information Ratio, and Consistency.
- **Passive Funds** are ranked purely by **Tracking Error** and **Expense Ratio**.

### 2. The Continuity Rule (Holdover vs. New Entrant) 🛡️
The system remembers previous results to prevent "serial switching."
- **Holdover 🛡️**: Fund was in the Top 3 last quarter. If it's still performing, **leave it alone**.
- **New Entrant 🌟**: Fund is new to the Top 3. Requires the **Manual Checklist** before capital is moved.

### 3. Smart Caching & Resource Efficiency ⚡
- **Daily Cache**: The UI detects if an analysis was already run today and loads results instantly.
- **Visual Feedback**: Real-time spinners indicate exactly when data is being fetched or prepared.
- **Auto-Retry**: Robust handling for flaky AMFI and NSE endpoints.

---

## 🧠 The Screening Strategy (v3)

### Phase 2: The Hard Elimination Gates
A fund that fails **any single gate** is immediately eliminated. There is no partial credit.

| Gate | Threshold | Rationale |
| :--- | :--- | :--- |
| **History** | ≥ 5 Years | Guarantees the fund has survived at least one full market cycle. |
| **AUM Bounds** | ₹500Cr - ₹50kCr | Prevents liquidity risk (too small) or mandate drift (too large). |
| **Negative Sharpe** | **Ratio > 0** | Disqualifies funds that returned less than risk-free T-bills (6.5%). |
| **Rel. Consistency** | ≥ 65% | Fund must beat its benchmark in at least 65% of 3-year rolling windows. |
| **Abs. Consistency** | ≥ 70% | Fund must deliver ≥ 12% CAGR in at least 70% of rolling windows. |
| **Capital Protection** | ≤ 5% | Max 1 in 20 rolling windows can result in a loss. |
| **Upside Capture** | ≥ 80 | Fund must participate in at least 80% of benchmark rallies. |
| **Down Capture** | Cat. Specific | Flexi Cap (<95), Mid Cap (<100), Small Cap (<105). |

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

### 2. Launch the Dashboard
The dashboard is the primary way to interact with the project. It handles caching, visualizes metrics, and allows manual email triggers.
```bash
python -m streamlit run app.py
```

### 3. CLI Power Tools
- `python main.py --dry`: Preview the full report in the console without sending emails.
- `python utils.py search "Parag Parikh"`: Find scheme codes for any fund.
- `python utils.py verify 122639`: Run a deep health check on a specific fund.
- `python check_env.py`: Diagnostic tool to verify your `.env` settings.

---

## 🤖 Automation (GitHub Actions)
The project includes a pre-configured workflow (`.github/workflows/quarterly.yml`) that runs on the **1st of every quarter** (Jan, Apr, Jul, Oct).

**To enable:**
1. Push code to a private GitHub repo.
2. Go to Settings > Secrets > Actions.
3. Add `MF_EMAIL_PASSWORD`, `EMAIL_SENDER`, and `SUBSCRIBERS`.

---

## 📂 Architecture Overview
- `app.py`: Streamlit Dashboard with smart caching and UI loaders.
- `screener.py`: The heart of the system. Implements Phase 2 gates and Phase 3 scoring.
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
