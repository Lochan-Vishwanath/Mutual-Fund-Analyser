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

## 🧠 How Screening Works (Strategy aligned)

### Phase 2 — Elimination (Hard Gates)
1.  **History**: Must have ≥ **5 years** of NAV history.
2.  **AUM**: Within category-specific bounds (e.g. Small Cap: ₹500Cr–₹12,000Cr).
3.  **Relative Consistency**: Beats benchmark in ≥ **65%** of 3-year rolling windows.
4.  **Absolute Consistency (Advisorkhoj logic)**: Annualized return ≥ **12%** in at least **70%** of 3-year rolling windows.
5.  **Capital Protection**: Negative returns in ≤ **5%** of 3-year rolling windows.
6.  **Down-Market Capture**: Within category threshold (e.g. Mid Cap < 100).

### Phase 3 — Weighted Scoring (Survivors Ranked)
- **20%** Rolling return consistency (Relative)
- **15%** Absolute return distribution (>12% bucket)
- **25%** Sortino ratio
- **20%** Information ratio
- **10%** Down-market capture (lower = better)
- **10%** Max drawdown (less negative = better)

**Passive (Index) funds:** Ranked purely by tracking error (lowest wins).

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
- `output/latest_results.json`: Persisted results from the last analysis run.

---

## 🤖 GitHub Actions Automation
Push this code to a private repo, add `MF_EMAIL_PASSWORD` to your GitHub Secrets, and the `.github/workflows/quarterly.yml` will automatically run the screening and email you on the 1st of every quarter (Jan, Apr, Jul, Oct).

---

## 💰 Cost: ₹0/month
Uses free public APIs and free-tier automation.

**Automated quarterly screening across ALL Indian mutual funds in each category**

No more manual candidate lists. Every quarter, the tool fetches every Direct Growth fund in each SEBI category from AMFI, runs the full Phase 2 + Phase 3 strategy on all of them, and sends a clean email with the top 3 per category.

---

## What Changed (v2)

| v1 (Old) | v2 (New) |
|----------|----------|
| You manually list 4–5 candidate funds per category | Screened against **every** Direct Growth fund in the AMFI category |
| Returns 1 winner | Returns **top 3 ranked** per category |
| Misses better funds that aren't on your radar | No fund in any category can slip through unnoticed |
| Winner changes only if you update your list | Winner updates automatically every quarter based on current performance |

---

## Quick Start

```bash
pip install requests pandas numpy

# 1. See how many funds will be screened per category
python utils.py count

# 2. Confirm benchmark scheme codes are correct
python utils.py search "Nifty Midcap 150 Index Fund Direct Growth"
python utils.py verify 135300

# 3. See all AMFI category names (helps configure categories in config.py)
python utils.py categories

# 4. Preview the full report (no email)
python utils.py preview

# 5. Run interactively (asks before sending)
python main.py
```

---

## Setup

### 1. Set benchmark codes in `config.py`

Benchmarks are index funds used to compute Alpha, Beta, Information Ratio, and Rolling Consistency for active funds. Get the right scheme codes:

```bash
python utils.py search "Nifty Midcap 150 Index Direct Growth"
python utils.py search "Nifty Smallcap 250 Index Direct Growth"
python utils.py search "Nifty 500 Index Fund Direct Growth"
python utils.py verify <code>   # verify the code shows 5+ years of data
```

### 2. Set email credentials

In `config.py`:
```python
EMAIL_SENDER = "yourname@gmail.com"
SUBSCRIBERS  = ["you@gmail.com", "family@gmail.com"]
```

Gmail App Password setup:
- Gmail → Account → Security → 2-Step Verification → App Passwords
- Create password for "Mail" → copy the 16-character password
- `export MF_EMAIL_PASSWORD="xxxx xxxx xxxx xxxx"`

### 3. Add/remove categories

Uncomment `Multi Cap` or `ELSS` in `config.py`, or add your own:

```python
"Contra Fund": {
    "strategy":               "active",
    "amfi_category_keywords": ["Contra Fund"],
    "name_must_contain":      [],
    "benchmark_code":         "147622",   # Nifty 500 proxy
    "aum_min":                500,
    "aum_max":                30000,
    "down_capture_max":       100,
    "min_history_years":      7,
},
```

---

## GitHub Actions (Fully Automated)

Push to a **private** GitHub repo, add one secret, and it runs on its own.

```
GitHub → Settings → Secrets → Actions → MF_EMAIL_PASSWORD = <your app password>
```

The workflow (`.github/workflows/quarterly.yml`) runs on Jan 1, Apr 1, Jul 1, Oct 1 at 8 AM IST.
Manual trigger available in the Actions tab.

---

## How Screening Works

**Phase 2 — Elimination (hard gates, any failure = cut):**
1. Must have ≥ 7 years of NAV history (configurable per category)
2. AUM within category-specific bounds (e.g. Small Cap: ₹500Cr–₹12,000Cr)
3. Active funds: 5-year rolling return consistency ≥ 75% vs. benchmark
4. Active funds: Down-market capture ratio within category threshold

**Phase 3 — Weighted Scoring (survivors ranked):**
- 35% Rolling return consistency
- 25% Sortino ratio
- 20% Information ratio
- 10% Down-market capture (lower = better)
- 10% Max drawdown (less negative = better)

**Passive (Index) funds:** Ranked purely by tracking error (lowest wins).

---

## Files

```
mf_tool/
├── config.py      ← EDIT THIS: categories, thresholds, email, weights
├── fetcher.py     ← Pulls all AMFI funds + NAV history + Nifty P/E
├── metrics.py     ← Computes Sharpe, Sortino, Alpha, Beta, IR, Rolling Consistency
├── screener.py    ← Phase 2 elimination + Phase 3 scoring → top 3
├── emailer.py     ← Builds HTML email + sends via Gmail
├── main.py        ← Orchestrator
├── utils.py       ← CLI tools (search, verify, categories, count, pe, preview)
├── requirements.txt
├── cache/         ← Auto-created: NAV cache (12hr TTL)
├── output/        ← Auto-created: saved HTML reports
└── .github/workflows/quarterly.yml
```

---

## Cost: ₹0/month
