# ─────────────────────────────────────────────────────────────────────────────
# main.py  —  Orchestrator.
#   python main.py          → interactive, asks before sending email
#   python main.py --auto   → GitHub Actions mode, sends automatically
#   python main.py --dry    → run screening + save HTML, never send
# ─────────────────────────────────────────────────────────────────────────────

import sys
import json
from datetime import date
from pathlib import Path
from screener import run_screening
from fetcher  import get_nifty_pe
from emailer  import build_html_email, send_email

# Custom JSON encoder for NumPy types
class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        import numpy as np
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        return super(NpEncoder, self).default(obj)

def run(send_mode: str = "ask"):
    """
    send_mode:
        "ask"  → print results, ask before sending
        "auto" → send automatically (GitHub Actions)
        "dry"  → never send, just save HTML and JSON
    """
    print("\n" + "=" * 65)
    print("  MF MASTER PLAN — QUARTERLY SCREENING")
    print(f"  {date.today().strftime('%d %B %Y')}")
    print("=" * 65)

    # 1. Run Screening (now saves JSON to output/latest_results.json inside run_screening)
    # Actually, we added saving logic to screener.py, so it's handled there.
    results  = run_screening()
    nifty_pe = get_nifty_pe()

    print(f"\n  Nifty 50 P/E: {nifty_pe:.2f}" if nifty_pe else "\n  Nifty 50 P/E: unavailable")

    html = build_html_email(results, nifty_pe)

    # Save HTML report
    out_dir = Path("./output")
    out_dir.mkdir(exist_ok=True)
    html_path = out_dir / f"report_{date.today().isoformat()}.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"\n  HTML report saved: {html_path}")

    # Console summary
    print("\n" + "=" * 65)
    print("  TOP FUNDS SUMMARY")
    print("=" * 65)
    for cat, data in results.items():
        top = data.get("top_funds", [])
        print(f"\n  [{cat}]  (screened {data['total_found']}, passed {data['total_passed_phase2']})")
        for i, f in enumerate(top, 1):
            rc  = f.get("rolling_consistency")
            sc  = f.get("total_score", 0)
            c5  = f.get("cagr_5y", 0)
            name_str = f['name'][:58]
            
            # Handle None values safely
            c5_str = f"{c5*100:.1f}%" if c5 is not None else "—"
            rc_str = f"{rc:.0%}" if rc is not None else "—"
            
            print(f"    #{i}: {name_str}")
            if rc:
                 print(f"        5Y CAGR: {c5_str}  |  Rolling: {rc_str}  |  Score: {sc:.2f}")
            else:
                 print(f"        5Y CAGR: {c5_str}")

    # Send
    if send_mode == "dry":
        print("\n  Dry run — email not sent.")
    elif send_mode == "auto":
        send_email(html)
    else:
        ans = input("\n  Send email to subscribers? (y/n): ").strip().lower()
        if ans == "y":
            send_email(html)
        else:
            print("  Email not sent.")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--auto" in args:
        run("auto")
    elif "--dry" in args:
        run("dry")
    else:
        run("ask")
# main.py  —  Orchestrator.
#   python main.py          → interactive, asks before sending email
#   python main.py --auto   → GitHub Actions mode, sends automatically
#   python main.py --dry    → run screening + save HTML, never send
# ─────────────────────────────────────────────────────────────────────────────

import sys
from datetime import date
from pathlib import Path
from screener import run_screening
from fetcher  import get_nifty_pe
from emailer  import build_html_email, send_email


def run(send_mode: str = "ask"):
    """
    send_mode:
        "ask"  → print results, ask before sending
        "auto" → send automatically (GitHub Actions)
        "dry"  → never send, just save HTML
    """
    print("\n" + "=" * 65)
    print("  MF MASTER PLAN — QUARTERLY SCREENING")
    print(f"  {date.today().strftime('%d %B %Y')}")
    print("=" * 65)

    results  = run_screening()
    nifty_pe = get_nifty_pe()

    print(f"\n  Nifty 50 P/E: {nifty_pe:.2f}" if nifty_pe else "\n  Nifty 50 P/E: unavailable")

    html = build_html_email(results, nifty_pe)

    # Save HTML report
    out_dir = Path("./output")
    out_dir.mkdir(exist_ok=True)
    html_path = out_dir / f"report_{date.today().isoformat()}.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"\n  HTML report saved: {html_path}")

    # Console summary
    print("\n" + "=" * 65)
    print("  TOP FUNDS SUMMARY")
    print("=" * 65)
    for cat, data in results.items():
        top = data.get("top_funds", [])
        print(f"\n  [{cat}]  (screened {data['total_found']}, passed {data['total_passed_phase2']})")
        for i, f in enumerate(top, 1):
            rc  = f.get("rolling_consistency")
            sc  = f.get("total_score", 0)
            c5  = f.get("cagr_5y", 0)
            print(f"    #{i}: {f['name'][:58]}")
            print(f"        5Y CAGR: {c5*100:.1f}%  |  Rolling: {rc:.0%}  |  Score: {sc:.2f}" if rc else
                  f"        5Y CAGR: {c5*100:.1f}%" if c5 else "        (metrics unavailable)")

    # Send
    if send_mode == "dry":
        print("\n  Dry run — email not sent.")
    elif send_mode == "auto":
        send_email(html)
    else:
        ans = input("\n  Send email to subscribers? (y/n): ").strip().lower()
        if ans == "y":
            send_email(html)
        else:
            print("  Email not sent.")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--auto" in args:
        run("auto")
    elif "--dry" in args:
        run("dry")
    else:
        run("ask")
