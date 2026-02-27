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
            st.success(f"✅ Loaded cached analysis from today ({file_date}).")
            results = load_data()
            st.session_state["results"] = results
            return

    with st.spinner("Running full screening… This takes 5–15 minutes."):
        prev_results = load_data()
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
        st.warning(f"⚠️ No funds passed criteria for {category}.")
        return

    st.subheader("🏆 Top Performers")
    rows = []
    for rank, f in enumerate(top_funds, 1):
        name = f.get("name", "—")
        mngr_warn = " ⚠️M" if f.get("manager_flag") else ""
        beta_warn = " ⚠️β" if f.get("beta_flag") else ""
        cont_badge = f" {f.get('continuity_status')}" if f.get("continuity_status") else ""
        
        rows.append({
            "Rank": f"#{rank}",
            "Fund": name[:60] + cont_badge + mngr_warn + beta_warn,
            "Score": f.get("total_score"),
            "Cat Pct": f.get("rolling_category_percentile"),
            "Rolling Cons.": f.get("rolling_consistency"),
            "Up Capture": f.get("up_capture"),
            "Down Capture": f.get("down_capture"),
            "Sortino": f.get("sortino"),
            "5Y CAGR": f.get("cagr_5y"),
            "10Y CAGR": f.get("cagr_10y"),
            "Max DD": f.get("max_drawdown"),
            "Alpha": f.get("alpha"),
            "Beta": f.get("beta"),
            "TER %": f.get("ter"),
            "AUM (Cr)": f.get("aum"),
        })

    if category_avg:
        rows.append({
            "Rank": "AVG", "Fund": "◆ Category Average", "Score": None, "Cat Pct": None,
            "Rolling Cons.": category_avg.get("rolling_consistency"),
            "Up Capture": category_avg.get("up_capture"), "Down Capture": category_avg.get("down_capture"),
            "Sortino": category_avg.get("sortino"), "5Y CAGR": category_avg.get("cagr_5y"),
            "10Y CAGR": None, "Max DD": category_avg.get("max_drawdown"),
            "Alpha": None, "Beta": None, "TER %": category_avg.get("ter"), "AUM (Cr)": None,
        })

    def fmt_row(row):
        return {
            "Rank": row["Rank"], "Fund": row["Fund"], "Score": _fmt(row["Score"]),
            "Cat Pct": f"{row['Cat Pct']:.0f}th" if row["Cat Pct"] is not None else "—",
            "Rolling Cons.": _fmt(row["Rolling Cons."], pct=True),
            "Up Capture": _fmt(row["Up Capture"], decimals=1),
            "Down Capture": _fmt(row["Down Capture"], decimals=1),
            "Sortino": _fmt(row["Sortino"]),
            "5Y CAGR": _fmt(row["5Y CAGR"], pct=True),
            "10Y CAGR": _fmt(row["10Y CAGR"], pct=True),
            "Max DD": _fmt(row["Max DD"], pct=True),
            "Alpha": _fmt(row["Alpha"], pct=True),
            "Beta": _fmt(row["Beta"]), "TER %": _fmt(row["TER %"]),
            "AUM (Cr)": f"₹{row['AUM (Cr)']:,.0f}" if row["AUM (Cr)"] else "—",
        }

    df_display = pd.DataFrame([fmt_row(r) for r in rows])
    def highlight_row(row):
        return ["background-color: #eef2f7; font-style: italic"] * len(row) if row["Rank"] == "AVG" else [""] * len(row)

    st.dataframe(df_display.style.apply(highlight_row, axis=1), use_container_width=True, hide_index=True)

    for f in top_funds:
        if f.get("manager_flag"):
            st.warning(f"⚠️ **Manager Flag** — {f['name'][:55]}: {f.get('manager_flag_reason')}")
        if f.get("beta_flag"):
            st.info(f"ℹ️ **High Beta** — {f['name'][:55]}: {f.get('beta_flag_reason')}")

    with st.expander("📋 Manual Verification Checklist"):
        st.markdown("""
1. **Fund Manager Tenure**: Is the manager who built the track record still there? (< 3y = risk).
2. **Sector Concentration**: No single sector > 35% of portfolio.
3. **Stock Concentration**: Top-10 holdings < 60% (avoid high conviction risk).
4. **Portfolio P/E**: Compare fund P/E vs benchmark P/E. Gap > 30% indicates style drift.
5. **SEBI Stress Test**: (Mid/Small Cap) Check days to liquidate 50% of portfolio.
6. **Switching Cost**: Always calculate Exit Load + LTCG/STCG impact before switching.
        """)

    if eliminated:
        with st.expander(f"❌ Eliminated Funds ({len(eliminated)}) — click to expand"):
            df_elim = pd.DataFrame([{"Fund": f.get("name", "")[:60], "Reason": f.get("reason", "")} for f in eliminated])
            st.dataframe(df_elim, use_container_width=True, hide_index=True)

def _render_passive_table(top_funds: list, eliminated: list, category: str):
    if not top_funds:
        st.warning(f"⚠️ No passive funds for {category}.")
        return

    st.subheader("🏆 Top Index Funds (Ranked by Tracking Error)")
    rows = []
    for rank, f in enumerate(top_funds, 1):
        rows.append({
            "Rank": f"#{rank}", "Fund": f.get("name", "—")[:65],
            "Tracking Error %": _fmt(f.get("tracking_error")),
            "3Y CAGR": _fmt(f.get("cagr_3y"), pct=True),
            "5Y CAGR": _fmt(f.get("cagr_5y"), pct=True),
            "Sharpe": _fmt(f.get("sharpe")),
            "Max DD": _fmt(f.get("max_drawdown"), pct=True),
            "TER %": _fmt(f.get("ter")),
            "AUM (Cr)": f"₹{f.get('aum', 0):,.0f}" if f.get("aum") else "—",
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    if eliminated:
        with st.expander(f"❌ Eliminated ({len(eliminated)})"):
            st.dataframe(pd.DataFrame([{"Fund": f.get("name","")[:60], "Reason": f.get("reason","")} for f in eliminated]), use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────────────────────────
# Main UI Flow
# ─────────────────────────────────────────────────────────────────────────────

st.title("📈 MF Master Plan v3 — Quarterly Screener")
st.markdown("Automated Mutual Fund screening based on v3 strategy: Risk-adjusted returns, Consistency, and Capture ratios.")

# -- Control Bar --
c1, c2, c3, _ = st.columns([1, 1, 1, 3])
with c1:
    if st.button("🚀 Run Analysis", help="Checks if data from today exists first"):
        run_analysis(force=False)
with c2:
    if st.button("🔄 Force Re-run", help="Fetch fresh data from API immediately"):
        run_analysis(force=True)

results = load_data()

with c3:
    if results and st.button("📧 Send Email", use_container_width=True):
        send_report_email(results)

if not results:
    st.info("No analysis data found. Click **Run Analysis** to start.")
    st.stop()

# -- Main Dashboard Section (Wrapped in Loader) --
with st.spinner("Fetching and preparing data..."):
    st.markdown("---")
    
    # 1. Summary Metrics
    total_screened = sum(cat.get("total_found", 0) for cat in results.values())
    total_passed   = sum(cat.get("total_passed_phase2", 0) for cat in results.values())
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Funds Screened", total_screened)
    m2.metric("Qualified", total_passed)
    m3.metric("Eliminated", total_screened - total_passed)
    last_run_dt = date.fromtimestamp(DATA_PATH.stat().st_mtime) if DATA_PATH.exists() else None
    m4.metric("Last Run", last_run_dt.strftime("%d %b %Y") if last_run_dt else "Never")

    # 2. Deployment Signal
    try:
        pe_val = get_nifty_pe()
        if pe_val:
            from config import PE_THRESHOLDS
            if pe_val >= PE_THRESHOLDS["overvalued"]:
                st.error(f"**Deployment Signal:** 🔴 OVERVALUED (P/E {pe_val:.1f}x) — SIPs only, no lump sum")
            elif pe_val >= PE_THRESHOLDS["fair_high"]:
                st.warning(f"**Deployment Signal:** 🟡 FAIR TO HIGH (P/E {pe_val:.1f}x) — Hold arbitrage buffer")
            elif pe_val >= PE_THRESHOLDS["fair_value"]:
                st.success(f"**Deployment Signal:** 🟢 FAIR VALUE (P/E {pe_val:.1f}x) — Deploy 25% of buffer")
            else:
                st.success(f"**Deployment Signal:** 🟢 ATTRACTIVE (P/E {pe_val:.1f}x) — Deploy aggressively")
    except:
        pass

    st.markdown("---")

    # 3. Process categories
    passive_cats = {k: v for k, v in results.items() if v.get("is_passive")}
    active_cats  = {k: v for k, v in results.items() if not v.get("is_passive")}

    # -- Special: Large Cap Active vs Passive Comparison --
    lc_active  = results.get("Large Cap (Active)")
    lc_passive = results.get("Large Cap (Passive)")

    if lc_active:  active_cats.pop("Large Cap (Active)", None)
    if lc_passive: passive_cats.pop("Large Cap (Passive)", None)
    passive_cats.pop("Large Cap / Index (Passive)", None) 

    if lc_active or lc_passive:
        st.markdown("## ⚔️ Large Cap: Active vs Passive")
        col_act, col_pas = st.columns(2)
        with col_act:
            st.markdown("### 🧠 Active Managers")
            if lc_active: _render_active_table(lc_active.get("top_funds", []), lc_active.get("eliminated", []), lc_active.get("category_avg", {}), "Large Cap (Active)")
            else: st.warning("No results.")
        with col_pas:
            st.markdown("### 🤖 Passive / Index")
            if lc_passive: _render_passive_table(lc_passive.get("top_funds", []), lc_passive.get("eliminated", []), "Large Cap (Passive)")
            else: st.warning("No results.")
        st.divider()

    # -- Active Category Tabs --
    if active_cats:
        st.markdown("## 🧠 Active Funds")
        act_tabs = st.tabs(list(active_cats.keys()))
        for i, (cat, data) in enumerate(active_cats.items()):
            with act_tabs[i]:
                _render_active_table(data.get("top_funds", []), data.get("eliminated", []), data.get("category_avg", {}), cat)

    # -- Passive Category Tabs --
    if passive_cats:
        st.markdown("## 📊 Passive / Index Funds")
        pass_tabs = st.tabs(list(passive_cats.keys()))
        for i, (cat, data) in enumerate(passive_cats.items()):
            with pass_tabs[i]:
                _render_passive_table(data.get("top_funds", []), data.get("eliminated", []), cat)

# -- Methodology Explainer (outside main spinner to keep it clean) --
with st.expander("ℹ️ How Scoring Works (v3 Strategy)"):
    st.markdown("""
### Phase 2 — Hard Elimination Gates
- **History**: ≥ 5 years NAV data.
- **AUM**: Category-specific bounds.
- **Sharpe**: Disqualify if negative.
- **Rolling Consistency**: Beats benchmark ≥ 65% of windows.
- **Upside Capture**: Participation ratio ≥ 80.
- **Downside Capture**: Within category threshold.

### Phase 3 — Weighted Scoring
- **Sortino**: 20%
- **Rolling Cons.**: 18%
- **Upside Capture**: 18%
- **Info Ratio**: 15%
- **Down Capture**: 15%
- **Max DD**: 9%
- **TER**: 5%
""")
