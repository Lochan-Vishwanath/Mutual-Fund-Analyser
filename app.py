# ─────────────────────────────────────────────────────────────────────────────
# app.py — Streamlit UI for MF Master Plan v4.0
#
# Features:
#   - Run Analysis button (uses cache if data from today already exists)
#   - Force Re-run button (always fetches fresh from API)
#   - Send Email button
#   - Large Cap Active vs Passive side-by-side comparison
#   - Per-category tabs for all other categories
#   - Phase 4 flags prominently shown
#   - Eliminated funds expandable section per category
#   - Score breakdown hover info
#   - Deployment signal banner
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

st.set_page_config(
    page_title="MF Master Plan v4",
    layout="wide",
    page_icon="📈",
    initial_sidebar_state="collapsed",
)

DATA_PATH = Path("output/latest_results.json")


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_data():
    if DATA_PATH.exists():
        try:
            with open(DATA_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return None


def run_analysis(force: bool = False):
    """Run screening. If force=False, uses cache if today's data exists."""
    if not force and DATA_PATH.exists():
        file_date = date.fromtimestamp(DATA_PATH.stat().st_mtime)
        if file_date == date.today():
            st.success(f"✅ Using cached results from today ({file_date}). Click **Force Re-run** to refresh.")
            st.session_state["results"] = load_data()
            return

    progress = st.progress(0, text="Starting screening pipeline...")
    with st.spinner("Running full screening — this takes 5–15 min (API rate-limited)..."):
        prev_results = load_data()
        results = run_screening(previous_results=prev_results)
        st.session_state["results"] = results
    progress.progress(100, text="Complete!")
    st.success("✅ Analysis complete!")
    st.rerun()


def send_report():
    results = load_data()
    if not results:
        st.error("No results to send — run analysis first.")
        return
    with st.spinner("Building and sending email..."):
        nifty_pe = get_nifty_pe()
        html     = build_html_email(results, nifty_pe)
        try:
            send_email(html)
            st.success("📧 Email sent successfully to all subscribers!")
        except Exception as e:
            st.error(f"Email failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Formatting helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(val, pct=False, decimals=2, na="—"):
    if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
        return na
    if pct:
        return f"{val:.1%}"
    return f"{val:.{decimals}f}"


def _score_bar(score: float, max_score: float = 4.0) -> str:
    """Returns a visual score bar string."""
    if score is None:
        return "—"
    pct = min(score / max_score, 1.0)
    filled = int(pct * 10)
    bar = "█" * filled + "░" * (10 - filled)
    return f"{bar} {score:.2f}"


# ─────────────────────────────────────────────────────────────────────────────
# Table renderers
# ─────────────────────────────────────────────────────────────────────────────

def _render_active_table(top_funds: list, eliminated: list, category_avg: dict,
                          category: str, rolling_window_years: int = 3,
                          consistency_floor: float = 0.55):
    if not top_funds:
        st.warning(f"⚠️ No funds passed all gates for **{category}** this quarter.")
        if eliminated:
            with st.expander(f"❌ See {len(eliminated)} eliminated funds"):
                df_elim = pd.DataFrame([
                    {"Fund": e.get("name", "")[:60], "Elimination Reason": e.get("reason", "")}
                    for e in eliminated
                ])
                st.dataframe(df_elim, use_container_width=True, hide_index=True)
        return

    rw_label = f"{rolling_window_years}yr rolling"

    # ── Top funds table ────────────────────────────────────────────────────
    rows = []
    for rank, f in enumerate(top_funds, 1):
        cont  = f.get("continuity_status", "")
        flags = []
        if f.get("manager_flag"):    flags.append("⚠️ MANAGER")
        if f.get("beta_flag"):       flags.append("⚡ BETA>1.3")
        if f.get("ptr_flag"):        flags.append("🔄 HIGH PTR")
        flag_str = " ".join(flags)

        pct = f.get("rolling_category_percentile")
        rows.append({
            "Rank":          f"#{rank}",
            "Fund":          f.get("name", "")[:55],
            "Status":        cont,
            "Flags":         flag_str or "✅ Clean",
            "Score /4":      _score_bar(f.get("total_score")),
            f"RC [{rw_label}]": _fmt(f.get("rolling_consistency"), pct=True),
            "Cat Pct":       f"{pct:.0f}th" if pct is not None else "—",
            "Cap. Ratio":    _fmt(f.get("capture_ratio"), decimals=3),
            "Up Capt.":      _fmt(f.get("up_capture"), decimals=1),
            "Dn Capt.":      _fmt(f.get("down_capture"), decimals=1),
            "Info Ratio":    _fmt(f.get("info_ratio")),
            "α Stability":   _fmt(f.get("alpha_stability"), decimals=4),
            "Sortino":       _fmt(f.get("sortino")),
            "5Y CAGR":       _fmt(f.get("cagr_5y"), pct=True),
            "10Y CAGR":      _fmt(f.get("cagr_10y"), pct=True),
            "Max DD":        _fmt(f.get("max_drawdown"), pct=True),
            "Alpha":         _fmt(f.get("alpha"), pct=True),
            "Beta":          _fmt(f.get("beta")),
            "TER %":         _fmt(f.get("ter")),
            "AUM (Cr)":      f"₹{f.get('aum', 0):,.0f}" if f.get("aum") else "—",
        })

    # Category average row
    if category_avg:
        rows.append({
            "Rank":          "AVG",
            "Fund":          "◆ Category Average",
            "Status":        "",
            "Flags":         "",
            "Score /4":      "",
            f"RC [{rw_label}]": _fmt(category_avg.get("rolling_consistency"), pct=True),
            "Cat Pct":       "—",
            "Cap. Ratio":    _fmt(category_avg.get("capture_ratio"), decimals=3),
            "Up Capt.":      _fmt(category_avg.get("up_capture"), decimals=1),
            "Dn Capt.":      _fmt(category_avg.get("down_capture"), decimals=1),
            "Info Ratio":    _fmt(category_avg.get("info_ratio")),
            "α Stability":   _fmt(category_avg.get("alpha_stability"), decimals=4),
            "Sortino":       _fmt(category_avg.get("sortino")),
            "5Y CAGR":       _fmt(category_avg.get("cagr_5y"), pct=True),
            "10Y CAGR":      "—",
            "Max DD":        _fmt(category_avg.get("max_drawdown"), pct=True),
            "Alpha":         "—",
            "Beta":          "—",
            "TER %":         _fmt(category_avg.get("ter")),
            "AUM (Cr)":      "—",
        })

    df_display = pd.DataFrame(rows)

    def _highlight(row):
        if row["Rank"] == "AVG":
            return ["background-color: #eef2f7; font-style: italic"] * len(row)
        if "⚠️" in str(row.get("Flags", "")) or "⚡" in str(row.get("Flags", "")):
            return ["background-color: #fff8e1"] * len(row)
        if "Holdover" in str(row.get("Status", "")):
            return ["background-color: #f0faf4"] * len(row)
        return [""] * len(row)

    st.dataframe(
        df_display.style.apply(_highlight, axis=1),
        use_container_width=True,
        hide_index=True,
    )

    # ── Flag detail cards ─────────────────────────────────────────────────
    for f in top_funds:
        if f.get("manager_flag"):
            st.warning(f"**⚠️ Manager Change Signal — {f['name'][:55]}**\n\n{f.get('manager_flag_reason', '')}")
        if f.get("beta_flag"):
            st.info(f"**⚡ High Beta — {f['name'][:55]}**\n\n{f.get('beta_flag_reason', '')}")
        if f.get("ptr_flag"):
            st.error(f"**🔄 High Portfolio Turnover — {f['name'][:55]}**\n\n{f.get('ptr_flag_reason', '')}")

    # ── Continuity desc ───────────────────────────────────────────────────
    for f in top_funds:
        cont   = f.get("continuity_status", "")
        desc   = f.get("continuity_desc", "")
        if desc:
            if "Holdover" in cont:
                st.success(f"**{cont} {f['name'][:50]}**: {desc}")
            else:
                st.warning(f"**{cont} {f['name'][:50]}**: {desc}")

    # ── Eliminated ────────────────────────────────────────────────────────
    if eliminated:
        with st.expander(f"❌ Eliminated Funds ({len(eliminated)}) — expand to see why"):
            df_elim = pd.DataFrame([
                {"Fund": e.get("name", "")[:60], "Reason": e.get("reason", "")}
                for e in eliminated
            ])
            st.dataframe(df_elim, use_container_width=True, hide_index=True)

    # ── Manual checklist ──────────────────────────────────────────────────
    with st.expander("📋 Manual Verification Checklist (for 🌟 New Entrants)"):
        st.markdown("""
1. **Fund Manager Tenure**: Is the manager who built this track record still there? (< 3 years = risk) — check AMC website.
2. **AUM Trajectory**: Has AUM doubled in the last 12 months? Could force mandate drift in Mid/Small Cap.
3. **Sector Concentration**: No single sector > 35% of portfolio.
4. **Portfolio P/E**: Compare fund P/E vs benchmark P/E. Gap > 30% = style drift or expensive positioning.
5. **SEBI Stress Test (Mid/Small Cap only)**: Check days-to-liquidate 50% of portfolio on the SEBI portal.
6. **Switching Cost**: Calculate Exit Load + LTCG (10% above ₹1L) / STCG (15%) before any switch.
7. **2-Quarter Rule**: Only exit a 🛡️ Holdover if it fails a gate for 2 consecutive quarters — a rank drop alone is not sufficient.
        """)


def _render_passive_table(top_funds: list, eliminated: list, category: str):
    if not top_funds:
        st.warning(f"⚠️ No passive funds found for {category}.")
        return

    st.caption("📊 Ranked by composite score: Tracking Error (70%) + TER (30%)")
    rows = []
    for rank, f in enumerate(top_funds, 1):
        cont = f.get("continuity_status", "")
        rows.append({
            "Rank":          f"#{rank}",
            "Fund":          f.get("name", "")[:65],
            "Status":        cont,
            "Score":         _score_bar(f.get("total_score")),
            "Tracking Err %": _fmt(f.get("tracking_error"), decimals=4),
            "3Y CAGR":       _fmt(f.get("cagr_3y"), pct=True),
            "5Y CAGR":       _fmt(f.get("cagr_5y"), pct=True),
            "Sharpe":        _fmt(f.get("sharpe")),
            "Max DD":        _fmt(f.get("max_drawdown"), pct=True),
            "TER %":         _fmt(f.get("ter")),
            "AUM (Cr)":      f"₹{f.get('aum', 0):,.0f}" if f.get("aum") else "—",
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    for f in top_funds:
        cont = f.get("continuity_status", "")
        desc = f.get("continuity_desc", "")
        if desc:
            if "Holdover" in cont:
                st.success(f"**{cont} {f['name'][:50]}**: {desc}")
            else:
                st.warning(f"**{cont} {f['name'][:50]}**: {desc}")

    if eliminated:
        with st.expander(f"❌ Eliminated ({len(eliminated)})"):
            df_elim = pd.DataFrame([
                {"Fund": e.get("name", "")[:60], "Reason": e.get("reason", "")}
                for e in eliminated
            ])
            st.dataframe(df_elim, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Main UI
# ─────────────────────────────────────────────────────────────────────────────

# ── Header ─────────────────────────────────────────────────────────────────
st.markdown("""
<div style="background:linear-gradient(135deg,#1B3A6B,#2C5F8A);padding:20px 24px;border-radius:8px;margin-bottom:16px">
  <h1 style="color:white;margin:0;font-size:24px">📈 MF Master Plan v4.0 — Quarterly Screener</h1>
  <p style="color:#aac4e8;margin:4px 0 0 0;font-size:13px">
    Active/Passive fork · 5-metric non-collinear scoring · Category-specific rolling windows · v4 architecture
  </p>
</div>
""", unsafe_allow_html=True)

# ── Control bar ─────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns([1, 1, 1, 3])

with c1:
    if st.button("🚀 Run Analysis", use_container_width=True,
                 help="Uses today's cache if available — avoids hitting APIs unnecessarily"):
        run_analysis(force=False)

with c2:
    if st.button("🔄 Force Re-run", use_container_width=True,
                 help="Ignores cache, fetches fresh data from all APIs"):
        run_analysis(force=True)

with c3:
    if st.button("📧 Send Email", use_container_width=True,
                 help="Sends the HTML report to all SUBSCRIBERS in .env"):
        send_report()

results = load_data()

if not results:
    st.info("No analysis data found. Click **Run Analysis** to start the screening pipeline.")
    
    # Show architecture summary while waiting
    with st.expander("📐 v4 Architecture Overview", expanded=True):
        st.markdown("""
        **Active/Passive Fork**: Large Cap Index funds scored on Tracking Error (70%) + TER (30%).
        All active categories go through the full 4-phase pipeline.
        
        **Phase 1 — Hard Filters**: History gate + category-specific AUM bounds  
        (e.g. Small Cap max ₹15,000 Cr · Flexi Cap no upper cap)
        
        **Phase 2 — Dynamic Gates**: Sharpe > 0 · TER gate · Rolling Consistency ≥55-60% · 
        Capital Protection ≤10% · Capture Ratio (÷) > 1.0  
        Mid/Small Cap use **5yr** rolling windows; Large/Flexi use **3yr**
        
        **Phase 3 — 5-Metric Scoring** (non-collinear):  
        IR 25% + Rolling Consistency 22% + Capture Ratio 20% + Sortino 18% + Alpha Stability 15%
        
        **Phase 4 — Flags**: Manager change (volatility signature + alpha flip) · High Beta · PTR · Continuity
        """)
    st.stop()

# ── Dashboard metrics ────────────────────────────────────────────────────────
total_screened = sum(cat.get("total_found", 0)         for cat in results.values())
total_passed   = sum(cat.get("total_passed_phase2", 0) for cat in results.values())
total_top      = sum(len(cat.get("top_funds", []))      for cat in results.values())
last_run_dt    = date.fromtimestamp(DATA_PATH.stat().st_mtime) if DATA_PATH.exists() else None

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Funds Screened",  total_screened)
m2.metric("Passed Gates",    total_passed)
m3.metric("Eliminated",      total_screened - total_passed)
m4.metric("Top Picks Total", total_top)
m5.metric("Last Run", last_run_dt.strftime("%d %b %Y") if last_run_dt else "Never")

# ── Deployment signal ────────────────────────────────────────────────────────
try:
    pe_val = get_nifty_pe()
    if pe_val:
        from config import PE_THRESHOLDS
        if pe_val >= PE_THRESHOLDS["overvalued"]:
            st.error(f"🔴 **Deployment: OVERVALUED** (P/E {pe_val:.1f}x) — SIPs only, no lump sum.")
        elif pe_val >= PE_THRESHOLDS["fair_high"]:
            st.warning(f"🟡 **Deployment: FAIR TO HIGH** (P/E {pe_val:.1f}x) — hold arbitrage buffer.")
        elif pe_val >= PE_THRESHOLDS["fair_value"]:
            st.success(f"🟢 **Deployment: FAIR VALUE** (P/E {pe_val:.1f}x) — deploy 25% of buffer.")
        else:
            st.success(f"🟢 **Deployment: ATTRACTIVE** (P/E {pe_val:.1f}x) — deploy aggressively.")
except Exception:
    pass

st.divider()

# ── Large Cap Active vs Passive (side by side) ───────────────────────────────
lc_active  = results.get("Large Cap (Active)")
lc_passive = results.get("Large Cap (Passive)")

if lc_active or lc_passive:
    st.markdown("## ⚔️ Large Cap: Active vs Passive")
    col_act, col_pas = st.columns(2)

    with col_act:
        st.markdown("### 🧠 Active Managers")
        if lc_active:
            rw  = lc_active.get("rolling_window_years", 3)
            cf  = lc_active.get("consistency_floor", 0.55)
            st.caption(f"AUM up to ₹80,000 Cr · {rw}yr rolling · consistency floor ≥{cf:.0%}")
            _render_active_table(
                lc_active.get("top_funds", []),
                lc_active.get("eliminated", []),
                lc_active.get("category_avg", {}),
                "Large Cap (Active)", rw, cf,
            )
        else:
            st.warning("No active large cap results.")

    with col_pas:
        st.markdown("### 🤖 Index / Passive")
        if lc_passive:
            st.caption("Ranked by Tracking Error (70%) + TER (30%) · No AUM max")
            _render_passive_table(
                lc_passive.get("top_funds", []),
                lc_passive.get("eliminated", []),
                "Large Cap (Passive)",
            )
        else:
            st.warning("No passive large cap results.")

    st.divider()

# ── Other active categories ───────────────────────────────────────────────────
active_cats = {
    k: v for k, v in results.items()
    if not v.get("is_passive") and k not in ("Large Cap (Active)", "Large Cap (Passive)")
}

if active_cats:
    st.markdown("## 🧠 Active Fund Categories")
    act_tabs = st.tabs(list(active_cats.keys()))
    for i, (cat, data) in enumerate(active_cats.items()):
        with act_tabs[i]:
            rw = data.get("rolling_window_years", 3)
            cf = data.get("consistency_floor", 0.55)
            st.caption(f"{rw}yr rolling windows · consistency floor ≥{cf:.0%} · "
                       f"{data.get('total_found',0)} screened, {data.get('total_passed_phase2',0)} qualified")
            _render_active_table(
                data.get("top_funds", []),
                data.get("eliminated", []),
                data.get("category_avg", {}),
                cat, rw, cf,
            )

# ── Other passive categories ──────────────────────────────────────────────────
passive_cats = {
    k: v for k, v in results.items()
    if v.get("is_passive") and k not in ("Large Cap (Active)", "Large Cap (Passive)")
}

if passive_cats:
    st.markdown("## 📊 Passive / Index Funds")
    pass_tabs = st.tabs(list(passive_cats.keys()))
    for i, (cat, data) in enumerate(passive_cats.items()):
        with pass_tabs[i]:
            st.caption(f"Passive scoring: TE 70% + TER 30%")
            _render_passive_table(
                data.get("top_funds", []),
                data.get("eliminated", []),
                cat,
            )

st.divider()

# ── Methodology expander ─────────────────────────────────────────────────────
with st.expander("ℹ️ v4 Scoring Architecture — Full Details"):
    st.markdown("""
    ### Active/Passive Fork
    Index funds skip Phases 2 & 3 entirely. They score on:
    - **Tracking Error (70%)** — lower = better replication quality
    - **TER (30%)** — lower = more return passed to investor
    
    ### Phase 1 — Static Hard Filters
    - **History gate**: ≥5yr (Large/Flexi), ≥7yr (Mid/Small Cap)
    - **AUM bounds**: Category-specific. Small Cap max ₹15,000 Cr. Flexi Cap: no upper cap.
    
    ### Phase 2 — Dynamic Gates (all category-relative)
    | Gate | Logic |
    |---|---|
    | Sharpe > 0 | Not beating the risk-free rate = not worth equity risk |
    | TER gate | TER > category median + 0.3% → eliminated (not just penalised) |
    | Rolling Consistency ≥55–60% AND above median | Consistency vs luck (survivorship bias compensated) |
    | Capital Protection ≤10% | ≤10% of rolling windows with negative returns |
    | Capture Ratio > 1.0 AND above median | Upside÷Downside > 1 = positive asymmetry |
    
    **Rolling window length**: 3yr for Large/Flexi Cap · 5yr for Mid/Small Cap  
    (Mid-cap cycles in India span 5–7 years; 3yr windows would capture bull-run luck as skill)
    
    ### Phase 3 — Weighted Scoring (5 dimensions)
    | Metric | Weight | Direction | What it Measures |
    |---|---|---|---|
    | Information Ratio | 25% | Higher | Alpha per unit of active risk (manager skill) |
    | Rolling Consistency | 22% | Higher | % windows beating benchmark (process > luck) |
    | Capture Ratio (÷) | 20% | Higher | Upside÷Downside asymmetry quality |
    | Sortino Ratio | 18% | Higher | Return per unit of downside vol only |
    | Alpha Stability | 15% | **Lower** | Rolling alpha stddev — consistent alpha generation |
    
    **Why division for Capture Ratio?** Subtraction hides magnitude: a fund with 90/80 capture and 
    130/120 capture both show spread=10, but behave very differently in a crash. Division:
    90/80=1.125 vs 130/120=1.083 — correctly shows the second fund has weaker asymmetry.
    
    **Why remove Max Drawdown?** It was 100% collinear with Sortino+Capture Ratio. Having all three
    meant downside risk had ~44% of the total weight. The v4 system measures 5 genuinely distinct things.
    
    ### Phase 4 — Qualitative Flags
    - **Manager Change**: 2 signals — volatility signature shift + alpha sign flip (not rank divergence)
    - **High Beta (>1.3)**: Fund amplifies market crashes significantly
    - **High PTR**: Turnover >1.5 SD above category median = hidden friction/impact costs
    - **🛡️ Holdover / 🌟 New Entrant**: Tax-aware continuity rule
    """)
