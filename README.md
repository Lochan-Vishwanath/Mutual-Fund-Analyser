# MF Master Plan Tool 🇮🇳
**Automated quarterly screening across ALL Indian mutual funds with Advisorkhoj-style Absolute Return logic.**

No more manual candidate lists. Every quarter, the tool fetches every Direct Growth fund in each SEBI category from AMFI, runs a rigorous Phase 2 (Elimination) + Phase 3 (Scoring) strategy, and presents the top 3 per category.

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Launch the Dashboard (Recommended)
Launch the interactive Streamlit UI to run analysis and view results visually:
```bash
python -m streamlit run app.py
```

### 3. CLI Usage
```bash
# Preview the full report in console (no email)
python main.py --dry

# Run interactively (asks before sending email)
python main.py

# Automated mode (used by GitHub Actions)
python main.py --auto
```

---

## 🛠 Setup

### 1. Set Benchmark Codes in `config.py`
Benchmarks are index funds used to compute Alpha, Beta, Information Ratio, and Rolling Consistency. Use the CLI to find the right codes:
```bash
python utils.py search "Nifty Midcap 150 Index Direct Growth"
python utils.py verify 149892   # verify the code shows 5+ years of data
```

### 2. Set Email Credentials
In `config.py`, set your `EMAIL_SENDER` and `SUBSCRIBERS`.
For Gmail, use an **App Password**:
- Gmail → Account → Security → 2-Step Verification → App Passwords
- Create password for "Mail"
- Set as env var: `export MF_EMAIL_PASSWORD="xxxx xxxx xxxx xxxx"`

---

## 🧠 How Screening Works (Strategy v3)

### Phase 2 — Elimination (Hard Gates)
1.  **History**: Must have ≥ **5 years** of NAV history.
2.  **AUM**: Within category-specific bounds (e.g. Small Cap: ₹500Cr–₹12,000Cr).
3.  **Negative Sharpe**: Any fund with a negative Sharpe ratio is immediately disqualified.
4.  **Relative Consistency**: Beats benchmark in ≥ **65%** of 3-year rolling windows.
5.  **Absolute Consistency (Advisorkhoj logic)**: Annualized return ≥ **12%** in at least **70%** of 3-year rolling windows.
6.  **Capital Protection**: Negative returns in ≤ **5%** of 3-year rolling windows.
7.  **Upside Capture**: Must participate in rallies (Ratio ≥ 80).
8.  **Down-Market Capture**: Within category threshold (e.g. Mid Cap < 100).

### Phase 3 — Weighted Scoring (Survivors Ranked)
- **18%** Rolling return consistency (Relative)
- **18%** Upside capture ratio (Higher = better)
- **20%** Sortino ratio (Higher = better)
- **15%** Information ratio (Higher = better)
- **15%** Down-market capture (Lower = better)
- **09%** Max drawdown (Less negative = better)
- **05%** Expense Ratio / TER (Lower = better)

**Passive (Index) funds:** Ranked purely by tracking error (lowest wins).

---

## 🚦 Phase 5: The Continuity Rule

The tool now remembers previous results to prevent "serial switching" (chasing the new #1).

*   **Holdover 🛡️**: Fund was in the Top 3 last quarter and remains there. **Safe to hold.**
*   **New Entrant 🌟**: Fund is new to the Top 3. **Verify manually before buying.**

**Switching Logic:**
> Do NOT switch just because a fund drops from #1 to #2. Only switch if a fund exits the Top 3 completely OR fails a hard gate (consistency drops, manager changes, etc.).

---

## 📋 Manual Verification (The "Human Loop")

The tool will flag these in the Email/UI for the Top 3 funds. You MUST verify them manually:

1.  **Fund Manager Tenure**: Is the manager who built the track record still there? (< 3 years = risk).
2.  **Sector Concentration**: No single sector > 35% of portfolio.
3.  **Stock Concentration**: Top-10 holdings < 60% (avoid high conviction bets).
4.  **Portfolio P/E**: Is it significantly higher (>30%) than the category average?
5.  **SEBI Stress Test**: (Mid/Small Cap) Days to liquidate 50% of portfolio.

---

## ⚔️ Special: Large Cap Active vs Passive
The tool identifies the inherent difficulty for active managers in the Large Cap space. It provides a dedicated **Winner's Circle** comparison:
- **Active Managers** are screened for Alpha and Consistency.
- **Passive Index Funds** are screened for low Tracking Error and Cost.
This helps you decide if it's worth paying active fees for potential alpha or simply tracking the index.

---

## ⚡ Performance & Caching
- **Smart Loading**: The UI checks if an analysis was already run today. If so, it loads the results instantly from cache, saving time and API resources.
- **Force Re-run**: You can override the cache with a single click if you need fresh mid-day data.
- **Visual Feedback**: Real-time loaders (spinners) indicate when data is being fetched or prepared.

---


## 📂 Project Structure
- `app.py`: Streamlit Web Dashboard (Run Analysis, View Results, Send Email).
- `config.py`: EDIT THIS for categories, thresholds, email, and weights.
- `metrics.py`: The Math Engine. Computes CAGR, Rolling Consistency, Capture Ratios, etc.
- `screener.py`: Orchestrates Phase 2 elimination and Phase 3 scoring.
- `fetcher.py`: Data ingestion from AMFI (funds/AUM) and mfapi.in (NAV).
- `emailer.py`: Builds and sends the HTML reports.
- `main.py`: CLI Orchestrator.
- `utils.py`: Utility CLI tools (search, verify, count, pe, etc.).
- `output/latest_results.json`: Persisted results from the last analysis run (used for Continuity checks).

---

## 🤖 GitHub Actions Automation
Push this code to a private repo, add `MF_EMAIL_PASSWORD` to your GitHub Secrets, and the `.github/workflows/quarterly.yml` will automatically run the screening and email you on the 1st of every quarter (Jan, Apr, Jul, Oct).

---

## 💰 Cost: ₹0/month
Uses free public APIs and free-tier automation.

