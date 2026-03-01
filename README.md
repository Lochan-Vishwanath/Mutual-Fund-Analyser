# MF Master Plan v4.0

Automated quarterly mutual fund screener for Indian equity funds. Runs the full v4 architecture — active/passive fork, 5-metric non-collinear scoring, category-specific rolling windows, and 4 qualitative flags.

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env        # fill in your Gmail + subscriber list
python utils.py config      # review all thresholds
python main.py --dry        # test run, no email
streamlit run app.py        # launch the Streamlit UI
```

## Architecture (v4)

### Active/Passive Fork
Index funds skip Phases 2 & 3 and score purely on:
- **Tracking Error (70%)** — replication quality
- **TER (30%)** — cost drag

### Phase 1 — Hard Filters
| Gate | Large/Flexi | Mid/Small |
|---|---|---|
| History | ≥5 years | ≥7 years |
| AUM min | ₹500–2000 Cr | ₹500 Cr |
| AUM max | ₹40–80k Cr (or none) | ₹15–25k Cr |

### Phase 2 — Dynamic Gates (all category-relative)
- Sharpe Ratio > 0
- TER ≤ category median + 0.3% (gate, not score)
- Rolling Consistency ≥ 55–60% AND above category median
- Capital Protection: negative windows ≤ 10%
- Capture Ratio (Upside÷Downside) > 1.0 AND above category median

**Rolling windows**: 3yr for Large/Flexi Cap · 5yr for Mid/Small Cap

### Phase 3 — Weighted Scoring (5 non-collinear dimensions)
| Metric | Weight |
|---|---|
| Information Ratio | 25% |
| Rolling Consistency | 22% |
| Capture Ratio (÷) | 20% |
| Sortino Ratio | 18% |
| Alpha Stability | 15% |

### Phase 4 — Qualitative Flags
- ⚠️ Manager Change: volatility signature shift + alpha sign flip
- ⚡ High Beta (>1.3)
- 🔄 High PTR: turnover >1.5 SD above category median
- 🛡️ Holdover / 🌟 New Entrant: tax-aware continuity rule

## CLI Tools

```bash
python utils.py search "HDFC Mid Cap"      # find scheme codes
python utils.py verify 120716              # check a benchmark code
python utils.py count                      # fund universe per category
python utils.py pe                         # Nifty P/E deployment signal
python utils.py config                     # print all v4 thresholds
python utils.py benchmark                  # show configured benchmarks
```

## GitHub Actions

Add these secrets in **Settings → Secrets → Actions**:
- `EMAIL_SENDER` — your Gmail address
- `MF_EMAIL_PASSWORD` — Gmail App Password (generate at myaccount.google.com/apppasswords)
- `SUBSCRIBERS` — comma-separated emails

The workflow fires automatically on **1 Jan, 1 Apr, 1 Jul, 1 Oct** at 7:30am IST.
You can also trigger it manually from the Actions tab.

## .env Setup

```env
MF_EMAIL_PASSWORD=your_gmail_app_password_here
EMAIL_SENDER=your_email@gmail.com
SUBSCRIBERS=you@gmail.com,family@gmail.com,friend@gmail.com
```

## Benchmark Code Verification

Always verify benchmark codes before running:
```bash
python utils.py search "Nifty 100 Index Fund Direct Growth"
python utils.py verify 120716
```

## The 2-Quarter Exit Rule

Only exit a 🛡️ Holdover fund if it **fails a gate** (not just drops in rank) for **2 consecutive quarters**.
A rank drop alone isn't sufficient reason — mean reversion and style rotations are normal.

The HTML report marks each top fund as Holdover or New Entrant. New Entrants require manual
verification before allocating capital. Check the checklist in the report footer.

## UI Metrics Guide

| Column | Meaning | Why it matters |
|---|---|---|
| **Score /4** | Overall Weighted Score | Our final "rank". 4.0 is the best in the category. |
| **RC [3yr rolling]** | Rolling Consistency | % of 3-year periods the fund beat its index. |
| **Cat Pct** | Category Percentile | Where this fund stands compared to peers (90th pct = Top 10%). |
| **Cap. Ratio** | Capture Ratio | **Upside ÷ Downside.** High means more offensive than defensive. |
| **Up / Dn Capt.** | Raw Capture % | How much the fund moves when the index moves 100%. |
| **Info Ratio** | Information Ratio | Pure measure of "Manager Skill" (Higher = More Skill). |
| **α Stability** | Alpha Stability | How stable the excess return is. Lower is better. |
| **Sortino** | Sortino Ratio | Return per unit of *bad* (downside) volatility. |
| **5Y / 10Y CAGR** | Compounded Returns | Standard annualized returns for these long periods. |
| **Max DD** | Max Drawdown | The "worst-case" drop from peak to trough. |
| **Alpha / Beta** | Regression Metrics | **Alpha:** Outperformance. **Beta:** Volatility relative to market. |
