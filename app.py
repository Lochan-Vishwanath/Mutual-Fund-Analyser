# ─────────────────────────────────────────────────────────────────────────────
# app.py — Streamlit Frontend for MF Master Plan v3
# ─────────────────────────────────────────────────────────────────────────────

import streamlit as st
import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import date
from screener import run_screening
from fetcher import get_nifty_pe
from emailer import build_html_email, send_email

st.set_page_config(page_title="MF Master Plan", layout="wide", page_icon="📈")

DATA_PATH = Path("output/latest_results.json")

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_data():
    if DATA_PATH.exists():
        try:
            with st.spinner("Loading data..."):
                with open(DATA_PATH, "r") as f:
                    return json.load(f)
        except:
            pass
    return None

    if DATA_PATH.exists():
        try:
            with open(DATA_PATH, "r") as f:
                return json.load(f)
        except:
            pass
    return None

def run_analysis(force=False):
    # Check if we have fresh data from today
    if not force and DATA_PATH.exists():
        file_date = date.fromtimestamp(DATA_PATH.stat().st_mtime)
        if file_date == date.today():
            st.success(f"✅ Loaded cached analysis from today ({file_date}). Use 'Force Run' to refresh.")
            results = load_data()
            st.session_state["results"] = results
            return

    with st.spinner("Running full screening… This takes 5–15 minutes depending on category size."):
        # Load previous results for continuity check
        prev_results = None
        if DATA_PATH.exists():
            try:
                with open(DATA_PATH, "r") as f:
                    prev_results = json.load(f)
            except: pass
            
        results = run_screening(previous_results=prev_results)
        st.session_state["results"] = results
        st.success("✅ Analysis complete!")
        st.rerun()

def send_report_email(results):
    with st.spinner("Sending email..."):
        nifty_pe = get_nifty_pe()
        html = build_html_email(results, nifty_pe)
        try:
            send_email(html)
            st.success("📧 Email sent successfully!")
        except Exception as e:
            st.error(f"Failed to send email: {e}")

def _fmt(val, pct=False, decimals=2, na="—"):
    if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
        return na
    if pct:
        return f"{val:.1%}"
    return f"{val:.{decimals}f}"

def _render_active_table(top_funds: list, eliminated: list, category_avg: dict, category: str):
    if not top_funds:
        st.warning("⚠️ No funds passed all Phase 2 criteria for this category.")
        return

    st.subheader("🏆 Top Performers")

    rows = []
    for rank, f in enumerate(top_funds, 1):
        name = f.get("name", "—")
        mngr_warn = " ⚠️M" if f.get("manager_flag") else ""
        beta_warn = " ⚠️β" if f.get("beta_flag") else ""
        cont_badge = f" {f.get('continuity_status')}" if f.get("continuity_status") else ""
        
        rows.append({
            "Rank":          f"#{rank}",
            "Fund":          name[:60] + cont_badge + mngr_warn + beta_warn,
            "Score":         f.get("total_score"),
            "Cat Pct":       f.get("rolling_category_percentile"),
            "Rolling Cons.": f.get("rolling_consistency"),
            "Up Capture":    f.get("up_capture"),
            "Down Capture":  f.get("down_capture"),
            "Sortino":       f.get("sortino"),
            "5Y CAGR":       f.get("cagr_5y"),
            "10Y CAGR":      f.get("cagr_10y"),
            "Max DD":        f.get("max_drawdown"),
            "Alpha":         f.get("alpha"),
            "Beta":          f.get("beta"),
            "TER %":         f.get("ter"),
            "AUM (Cr)":      f.get("aum"),
        })

    if category_avg:
        rows.append({
            "Rank":          "AVG",
            "Fund":          "◆ Category Average",
            "Score":         None,
            "Cat Pct":       None,
            "Rolling Cons.": category_avg.get("rolling_consistency"),
            "Up Capture":    category_avg.get("up_capture"),
            "Down Capture":  category_avg.get("down_capture"),
            "Sortino":       category_avg.get("sortino"),
            "5Y CAGR":       category_avg.get("cagr_5y"),
            "10Y CAGR":      None,
            "Max DD":        category_avg.get("max_drawdown"),
            "Alpha":         None,
            "Beta":          None,
            "TER %":         category_avg.get("ter"),
            "AUM (Cr)":      None,
        })

    def fmt_row(row):
        return {
            "Rank":          row["Rank"],
            "Fund":          row["Fund"],
            "Score":         _fmt(row["Score"]),
            "Cat Pct":       f"{row['Cat Pct']:.0f}th" if row["Cat Pct"] is not None else "—",
            "Rolling Cons.": _fmt(row["Rolling Cons."], pct=True),
            "Up Capture":    _fmt(row["Up Capture"], decimals=1),
            "Down Capture":  _fmt(row["Down Capture"], decimals=1),
            "Sortino":       _fmt(row["Sortino"]),
            "5Y CAGR":       _fmt(row["5Y CAGR"], pct=True),
            "10Y CAGR":      _fmt(row["10Y CAGR"], pct=True),
            "Max DD":        _fmt(row["Max DD"], pct=True),
            "Alpha":         _fmt(row["Alpha"], pct=True),
            "Beta":          _fmt(row["Beta"]),
            "TER %":         _fmt(row["TER %"]),
            "AUM (Cr)":      f"₹{row['AUM (Cr)']:,.0f}" if row["AUM (Cr)"] else "—",
        }

    df_display = pd.DataFrame([fmt_row(r) for r in rows])

    def highlight_row(row):
        styles = [""] * len(row)
        if row["Rank"] == "AVG":
            return ["background-color: #eef2f7; font-style: italic"] * len(row)
        return styles

    st.dataframe(df_display.style.apply(highlight_row, axis=1), use_container_width=True, hide_index=True)

    for f in top_funds:
        if f.get("manager_flag"):
            st.warning(f"⚠️ **Manager Flag** — {f['name'][:55]}: {f.get('manager_flag_reason')}")
        if f.get("beta_flag"):
            st.info(f"ℹ️ **High Beta** — {f['name'][:55]}: {f.get('beta_flag_reason')}")

    with st.expander("📋 Manual Checks Required Before Investing"):
        st.markdown("""
For each fund in the top 3, **manually verify** on the AMC's factsheet or Value Research / Morningstar:

1. **Fund Manager Tenure**: Is the same manager listed who built this track record? Manager changes invalidate historical metrics.
2. **Sector Concentration**: No single sector > 35% of portfolio?
3. **Stock Concentration**: Top-10 holdings < 70% of portfolio? (High = concentrated, single-stock risk)
4. **Portfolio P/E vs Category**: Is the fund's portfolio P/E in line with peers?
5. **SEBI Stress Test** (Mid/Small Cap only): Check how many days to liquidate 50% of the portfolio.
6. **Exit Load & Lock-in**: Verify exit load period before switching.
7. **Tax Impact**: If switching, compute LTCG/STCG before acting.
        """)

    if eliminated:
        reason_counts = {}
        for f in eliminated:
            reason = f.get("reason", "Unknown")[:50]
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

        with st.expander(f"❌ Eliminated Funds ({len(eliminated)}) — click to expand"):
            st.markdown("**Elimination Reasons:**")
            for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1])[:10]:
                st.markdown(f"- {reason}: **{count}** fund(s)")
            st.divider()
            df_elim = pd.DataFrame([{"Fund": f.get("name", "")[:60], "Reason": f.get("reason", "")} for f in eliminated])
            st.dataframe(df_elim, use_container_width=True, hide_index=True)

def _render_passive_table(top_funds: list, eliminated: list, category: str):
    if not top_funds:
        st.warning("⚠️ No passive funds found for this category.")
        return

    st.subheader("🏆 Top Index Funds (Ranked by Tracking Error)")

    rows = []
    for rank, f in enumerate(top_funds, 1):
        rows.append({
            "Rank":               f"#{rank}",
            "Fund":               f.get("name", "—")[:65],
            "Tracking Error %":   _fmt(f.get("tracking_error")),
            "3Y CAGR":            _fmt(f.get("cagr_3y"), pct=True),
            "5Y CAGR":            _fmt(f.get("cagr_5y"), pct=True),
            "Sharpe":             _fmt(f.get("sharpe")),
            "Max DD":             _fmt(f.get("max_drawdown"), pct=True),
            "TER %":              _fmt(f.get("ter")),
            "AUM (Cr)":           f"₹{f.get('aum', 0):,.0f}" if f.get("aum") else "—",
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with st.expander(f"❌ Eliminated ({len(eliminated)})"):
        if eliminated:
            st.dataframe(
                pd.DataFrame([{"Fund": f.get("name","")[:60], "Reason": f.get("reason","")} for f in eliminated]),
                use_container_width=True, hide_index=True
            )

# ─────────────────────────────────────────────────────────────────────────────
# Main UI
# ─────────────────────────────────────────────────────────────────────────────

st.title("📈 MF Master Plan v3 — Quarterly Screener")
st.markdown(
    "Automated mutual fund screening: Phase 2 elimination + Phase 3 weighted scoring. "
    "Every Direct Growth fund in each SEBI category is screened. No manual candidate lists."
)

# ── Controls ─────────────────────────────────────────────────────────────────
ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns([1, 1, 1, 3])
with ctrl_col1:
    if st.button("🚀 Run Analysis", help="Runs only if no data for today"):
        run_analysis(force=False)

with ctrl_col2:
    if st.button("🔄 Force Re-run", help="Force fresh analysis even if data exists"):
        run_analysis(force=True)

results = load_data()

with ctrl_col3:
    if results and st.button("📧 Send Email", use_container_width=True):
        send_report_email(results)

if not results:
    st.info("No analysis data found. Click **Run Analysis** to start.")
    st.stop()

st.markdown("---")

# ── Summary Metrics ───────────────────────────────────────────────────────────
total_screened = sum(cat.get("total_found", 0) for cat in results.values())
total_passed   = sum(cat.get("total_passed_phase2", 0) for cat in results.values())

m1, m2, m3, m4 = st.columns(4)
m1.metric("Funds Screened",      total_screened)
m2.metric("Qualified (Phase 2)", total_passed)
m3.metric("Eliminated",          total_screened - total_passed)
m4.metric("Last Run",            date.fromtimestamp(DATA_PATH.stat().st_mtime).strftime("%d %b %Y") if DATA_PATH.exists() else "Never")

st.markdown("---")

# ── Nifty P/E Signal ─────────────────────────────────────────────────────────
try:
    pe_val = get_nifty_pe()
    if pe_val:
        from config import PE_THRESHOLDS
        if pe_val >= PE_THRESHOLDS["overvalued"]:
            pe_signal, pe_color = f"🔴 OVERVALUED (P/E {pe_val:.1f}x) — SIPs only, no lump sum", "error"
        elif pe_val >= PE_THRESHOLDS["fair_high"]:
            pe_signal, pe_color = f"🟡 FAIR TO HIGH (P/E {pe_val:.1f}x) — Hold arbitrage buffer", "warning"
        elif pe_val >= PE_THRESHOLDS["fair_value"]:
            pe_signal, pe_color = f"🟢 FAIR VALUE (P/E {pe_val:.1f}x) — Deploy 25% of buffer", "success"
        else:
            pe_signal, pe_color = f"🟢 ATTRACTIVE (P/E {pe_val:.1f}x) — Deploy aggressively", "success"

        if pe_color == "error":     st.error(f"**Deployment Signal:** {pe_signal}")
        elif pe_color == "warning": st.warning(f"**Deployment Signal:** {pe_signal}")
        else:                       st.success(f"**Deployment Signal:** {pe_signal}")
except Exception:
    pass

# ── Process Categories ───────────────────────────────────────────────────────
passive_cats = {k: v for k, v in results.items() if v.get("is_passive")}
active_cats  = {k: v for k, v in results.items() if not v.get("is_passive")}

# ── Special: Large Cap Active vs Passive Comparison ─────────────────────────
lc_active  = results.get("Large Cap (Active)")
lc_passive = results.get("Large Cap (Passive)")

# Remove from standard lists
if lc_active:  active_cats.pop("Large Cap (Active)", None)
if lc_passive: passive_cats.pop("Large Cap (Passive)", None)
# Legacy key cleanup
passive_cats.pop("Large Cap / Index (Passive)", None) 

if lc_active or lc_passive:
    st.markdown("## ⚔️ Large Cap: Active vs Passive")
    st.info("Direct comparison of top Active Managers vs low-cost Index Funds.")
    
    col_act, col_pas = st.columns(2)
    
    with col_act:
        st.markdown("### 🧠 Active Managers")
        if lc_active:
            _render_active_table(
                lc_active.get("top_funds", []),
                lc_active.get("eliminated", []),
                lc_active.get("category_avg", {}),
                "Large Cap (Active)"
            )
        else:
            st.warning("No Active Large Cap results.")

    with col_pas:
        st.markdown("### 🤖 Passive / Index")
        if lc_passive:
            _render_passive_table(
                lc_passive.get("top_funds", []),
                lc_passive.get("eliminated", []),
                "Large Cap (Passive)"
            )
        else:
            st.warning("No Passive Large Cap results.")
    
    st.divider()

# ── Active Funds Tabs ───────────────────────────────────────────────────────
if active_cats:
    st.markdown("## 🧠 Active Funds")
    act_tabs = st.tabs(list(active_cats.keys()))
    for i, (cat, data) in enumerate(active_cats.items()):
        with act_tabs[i]:
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Screened",   data.get("total_found", 0))
            col_b.metric("Qualified",  data.get("total_passed_phase2", 0))
            col_c.metric("Top Shown",  min(3, len(data.get("top_funds", []))))
            _render_active_table(
                data.get("top_funds", []),
                data.get("eliminated", []),
                data.get("category_avg", {}),
                cat,
            )

# ── Passive Funds Tabs ──────────────────────────────────────────────────────
if passive_cats:
    st.markdown("## 📊 Passive / Index Funds")
    pass_tabs = st.tabs(list(passive_cats.keys()))
    for i, (cat, data) in enumerate(passive_cats.items()):
        with pass_tabs[i]:
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Screened",   data.get("total_found", 0))
            col_b.metric("Qualified",  data.get("total_passed_phase2", 0))
            col_c.metric("Top Shown",  min(3, len(data.get("top_funds", []))))
            _render_passive_table(
                data.get("top_funds", []),
                data.get("eliminated", []),
                cat,
            )

# ── Methodology Explainer ───────────────────────────────────────────────────
with st.expander("ℹ️ How Scoring Works (v3 Strategy)"):
    st.markdown("""
### Phase 2 — Hard Elimination Gates
Any fund failing even one gate is eliminated:

| Gate | Threshold |
|---|---|
| History | ≥ 5 years NAV data |
| AUM | Category-specific min/max bounds |
| Rolling Consistency | ≥ 65% of 3Y windows beat benchmark |
| Absolute Consistency | ≥ 70% of 3Y windows achieve ≥ 12% CAGR |
| Capital Protection | ≤ 5% of 3Y windows have negative returns |
| **Upside Capture (NEW)** | **≥ 80 — must participate in benchmark rallies** |
| Down-Market Capture | Category-specific max (95–105) |

### Phase 3 — Weighted Scoring (Survivors Only)

| Metric | Weight | Direction |
|---|---|---|
| Rolling Consistency | 18% | Higher = better |
| Sortino Ratio | 20% | Higher = better |
| Information Ratio | 15% | Higher = better |
| **Upside Capture (NEW)** | **18%** | **Higher = better** |
| Down Capture | 15% | Lower = better |
| Max Drawdown | 9% | Less negative = better |
| **TER / Expense Ratio (NEW)** | **5%** | **Lower = better** |
""")
