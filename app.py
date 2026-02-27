# ─────────────────────────────────────────────────────────────────────────────
# app.py — Streamlit Frontend for MF Master Plan
# ─────────────────────────────────────────────────────────────────────────────
import streamlit as st
import pandas as pd
import json
import os
from pathlib import Path
from screener import run_screening
from fetcher import get_nifty_pe
from emailer import build_html_email, send_email
from datetime import date

st.set_page_config(page_title="MF Master Plan", layout="wide", page_icon="📈")

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

DATA_PATH = Path("output/latest_results.json")

def load_data():
    if DATA_PATH.exists():
        with open(DATA_PATH, "r") as f:
            return json.load(f)
    return None

def run_analysis():
    with st.spinner('Running analysis... This may take a few minutes.'):
        results = run_screening()
        st.session_state['results'] = results
        st.success("Analysis complete! Data saved.")
        st.rerun()

def send_report_email(results):
    with st.spinner('Sending email...'):
        nifty_pe = get_nifty_pe()
        html = build_html_email(results, nifty_pe)
        try:
            send_email(html)
            st.success("Email sent successfully!")
        except Exception as e:
            st.error(f"Failed to send email: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────────────────────

st.title("📈 MF Master Plan — Quarterly Screener")
st.markdown("Automated mutual fund screening based on rigorous Phase 2 & 3 criteria.")

col1, col2 = st.columns([1, 4])

with col1:
    if st.button("🔄 Run New Analysis", use_container_width=True):
        run_analysis()

results = load_data()

if results:
    if st.button("📧 Send Email Report", use_container_width=True):
        send_report_email(results)
        
    st.markdown("---")
    
    # Summary Metrics
    total_screened = sum(cat['total_found'] for cat in results.values())
    total_passed = sum(cat['total_passed_phase2'] for cat in results.values())
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Funds Screened", total_screened)
    m2.metric("Funds Qualified", total_passed)
    m3.metric("Last Run", date.today().strftime("%Y-%m-%d")) # Ideally save run date in json

    st.markdown("### Category Results")
    
    tabs = st.tabs(list(results.keys()))
    
    for i, (category, data) in enumerate(results.items()):
        with tabs[i]:
            st.header(f"{category}")
            
            top_funds = data.get('top_funds', [])
            eliminated = data.get('eliminated', [])
            
            # Top Funds Table
            if top_funds:
                st.subheader("🏆 Top Performers")
                
                # Flatten dicts for display
                df_top = pd.DataFrame(top_funds)
                
                # Select columns to display
                cols = ['name', 'total_score', 'rolling_consistency', 'absolute_consistency', 'capital_protection', 'cagr_5y', 'sortino', 'max_drawdown', 'down_capture']
                
                # Check if columns exist (passive might not have all)
                cols = [c for c in cols if c in df_top.columns]
                
                # Rename for cleaner display
                rename_map = {
                    'name': 'Fund Name',
                    'total_score': 'Score',
                    'rolling_consistency': 'Rel. Consistency',
                    'absolute_consistency': 'Abs. >12%',
                    'capital_protection': 'Negative Ret',
                    'cagr_5y': '5Y CAGR',
                    'sortino': 'Sortino',
                    'max_drawdown': 'Max DD',
                    'down_capture': 'Down Cap'
                }
                
                st.dataframe(
                    df_top[cols].rename(columns=rename_map).style.format({
                        'Score': '{:.2f}',
                        'Rel. Consistency': lambda x: f'{x:.1%}' if pd.notnull(x) else '—',
                        'Abs. >12%': lambda x: f'{x:.1%}' if pd.notnull(x) else '—',
                        'Negative Ret': lambda x: f'{x:.1%}' if pd.notnull(x) else '—',
                        '5Y CAGR': lambda x: f'{x:.1%}' if pd.notnull(x) else '—',
                        'Sortino': lambda x: f'{x:.2f}' if pd.notnull(x) else '—',
                        'Max DD': lambda x: f'{x:.1%}' if pd.notnull(x) else '—',
                        'Down Cap': lambda x: f'{x:.1f}' if pd.notnull(x) else '—'
                    }),
                    use_container_width=True
                )
            else:
                st.warning("No funds passed the criteria for this category.")

            # Eliminated Section
            with st.expander(f"❌ Eliminated Funds ({len(eliminated)})"):
                if eliminated:
                    df_elim = pd.DataFrame(eliminated)
                    st.dataframe(
                        df_elim[['name', 'reason']].rename(columns={'name': 'Fund Name', 'reason': 'Elimination Reason'}),
                        use_container_width=True
                    )
                else:
                    st.info("No funds eliminated.")

else:
    st.info("No analysis data found. Click 'Run New Analysis' to start.")
