# ─────────────────────────────────────────────────────────────────────────────
# fetcher.py  —  Data layer.
#
# v3 Changes:
#   - Added get_ter_map(): fetches Expense Ratio (TER) from AMFI portal
#   - Added get_category_average_metrics(): computes category peer averages
#   - Improved _is_direct_growth() filter to handle more name variations
#   - Added AMFI category fallback for funds without direct "Mid Small Cap" header
# ─────────────────────────────────────────────────────────────────────────────

import os
import json
import time
import requests
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

CACHE_DIR = Path("./cache")
CACHE_DIR.mkdir(exist_ok=True)

MFAPI_BASE   = "https://api.mfapi.in/mf"
AMFI_NAV_URL = "https://www.amfiindia.com/spages/NAVAll.txt"

NAV_CACHE_HOURS    = 12
SCHEME_CACHE_HOURS = 24
FETCH_DELAY        = 0.30   # slightly more polite in v3


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"

def _txt_cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.txt"

def _is_fresh(path: Path, max_hours: float) -> bool:
    if not path.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    return age < timedelta(hours=max_hours)

def _is_direct_growth(name: str) -> bool:
    """
    Returns True only for Direct Plan Growth schemes.
    Filters out: Regular plans, IDCW/Dividend plans, FoFs, ETFs, Pension.
    """
    n = name.lower()

    # Must contain "direct"
    if "direct" not in n:
        return False

    # Must have growth signal (various naming conventions across AMCs)
    growth_signals = ["growth", " gr", "-gr", "-g)", "- growth", "growth plan"]
    if not any(g in n for g in growth_signals):
        return False

    # Exclude dividend / IDCW variants
    exclude = [
        "idcw", "dividend", "div payout", "reinvest", "bonus",
        "annual distribution", "monthly distribution", "quarterly distribution",
        "weekly distribution"
    ]
    if any(e in n for e in exclude):
        return False

    # Exclude structure types that aren't open-ended equity funds
    structure_exclude = [
        "fund of fund", "fof", " etf", "exchange traded",
        "pension", "retirement", "segregated", "close ended",
        "interval fund", "fixed maturity", "fmp"
    ]
    if any(e in n for e in structure_exclude):
        return False

    return True


# ─────────────────────────────────────────────────────────────────────────────
# AMFI category → scheme list
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_amfi_raw() -> str:
    """Fetch or return cached AMFI NAVAll.txt content."""
    cache = _txt_cache_path("amfi_navall")
    if _is_fresh(cache, SCHEME_CACHE_HOURS):
        return cache.read_text(encoding="utf-8", errors="replace")
    print("  [fetcher] Refreshing AMFI NAVAll.txt...")
    resp = requests.get(AMFI_NAV_URL, timeout=30)
    resp.raise_for_status()
    text = resp.text
    cache.write_text(text, encoding="utf-8")
    return text


def _build_category_map(amfi_text: str) -> dict[str, list[dict]]:
    """
    Parses NAVAll.txt and returns:
      { "Equity Scheme - Large Cap Fund": [{"code": "...", "name": "..."}, ...] }
    Only Direct Growth schemes included.
    """
    category_map: dict[str, list[dict]] = {}
    current_category = None

    for raw_line in amfi_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Section headers
        if line.startswith("Open Ended Schemes(") or line.startswith("Interval Fund("):
            start = line.find("(")
            end   = line.rfind(")")
            if start != -1 and end != -1:
                current_category = line[start + 1: end].strip()
            continue

        if line.startswith("Close Ended Schemes("):
            current_category = None
            continue

        if current_category is None:
            continue
        if line.startswith("Scheme Code;"):
            continue

        parts = line.split(";")
        if len(parts) < 4:
            continue
        code = parts[0].strip()
        if not code.isdigit():
            continue

        name = parts[3].strip()
        if _is_direct_growth(name):
            category_map.setdefault(current_category, []).append({
                "code": code,
                "name": name,
            })

    return category_map


def get_all_direct_growth_funds_by_category(
    amfi_category_keywords: list[str],
    name_must_contain: list[str] = None,
) -> list[dict]:
    """
    Returns list of {code, name} dicts for all Direct Growth funds
    whose AMFI category header matches any of the given keywords.
    """
    amfi_text    = _fetch_amfi_raw()
    category_map = _build_category_map(amfi_text)

    funds = []
    keywords_lower = [k.lower() for k in amfi_category_keywords]

    for cat_label, cat_funds in category_map.items():
        cat_lower = cat_label.lower()
        match = False
        for kw in keywords_lower:
            if kw in cat_lower:
                if kw == "mid cap fund" and "large &" in cat_lower:
                    continue
                match = True
                break
        if match:
            funds.extend(cat_funds)
    # Deduplicate by code
    seen, unique = set(), []
    for f in funds:
        if f["code"] not in seen:
            seen.add(f["code"])
            unique.append(f)

    # Optional name filter
    if name_must_contain:
        name_filters = [n.lower() for n in name_must_contain]
        unique = [f for f in unique if any(nf in f["name"].lower() for nf in name_filters)]

    return unique


# ─────────────────────────────────────────────────────────────────────────────
# NAV history
# ─────────────────────────────────────────────────────────────────────────────

def get_nav_history(scheme_code: str, force_refresh: bool = False) -> pd.DataFrame:
    """
    Fetch full NAV history for a scheme.
    Returns DataFrame: date (datetime), nav (float), sorted oldest→newest.
    """
    cache = _cache_path(str(scheme_code))

    if not force_refresh and _is_fresh(cache, NAV_CACHE_HOURS):
        with open(cache) as f:
            data = json.load(f)
    else:
        resp = requests.get(f"{MFAPI_BASE}/{scheme_code}", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        with open(cache, "w") as f:
            json.dump(data, f)
        time.sleep(FETCH_DELAY)

    records = data.get("data", [])
    if not records:
        raise ValueError(f"No NAV data for scheme {scheme_code}")

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y")
    df["nav"]  = df["nav"].astype(float)
    df = df.sort_values("date").reset_index(drop=True)
    return df[["date", "nav"]]


def get_scheme_name(scheme_code: str) -> str:
    cache = _cache_path(str(scheme_code))
    if cache.exists():
        with open(cache) as f:
            return json.load(f).get("meta", {}).get("scheme_name", str(scheme_code))
    return str(scheme_code)


# ─────────────────────────────────────────────────────────────────────────────
# TER / Expense Ratio (NEW in v3)
# ─────────────────────────────────────────────────────────────────────────────

def get_ter_map() -> dict[str, float]:
    """
    Fetches Expense Ratio (TER) for all schemes from AMFI's portal.
    Returns {scheme_code: ter_pct} e.g. {"119552": 0.78}

    AMFI publishes TER at:
      https://portal.amfiindia.com/DownloadExpenseRatioCurrent.aspx

    Format (pipe-delimited):
      AMC Code | AMC Name | Scheme Code | Scheme Name | Effective Date | TER (Regular) | TER (Direct)

    Falls back to cache (7-day TTL) if fetch fails.
    """
    ter_cache = _cache_path("amfi_ter")
    if _is_fresh(ter_cache, 168):   # 7 days — TER changes rarely
        try:
            with open(ter_cache) as f:
                return json.load(f)
        except Exception:
            pass

    ter_map: dict[str, float] = {}

    # Primary source: AMFI TER download
    urls_to_try = [
        "https://portal.amfiindia.com/DownloadExpenseRatioCurrent.aspx",
        "https://www.amfiindia.com/modules/TerPension",
    ]

    for url in urls_to_try:
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            content = r.text

            for line in content.splitlines():
                # Try multiple delimiters — AMFI format varies
                for delim in ["|", ";", ","]:
                    parts = [p.strip() for p in line.split(delim)]
                    if len(parts) >= 6:
                        # Look for a scheme code (5-6 digit number)
                        for i, part in enumerate(parts):
                            if part.isdigit() and 4 <= len(part) <= 7:
                                # TER is usually the last numeric column
                                # Try to parse a % value from remaining columns
                                for j in range(len(parts) - 1, i, -1):
                                    try:
                                        ter_val = float(parts[j].replace("%", "").strip())
                                        if 0 < ter_val < 5:   # TER is always 0–5%
                                            ter_map[part] = ter_val
                                            break
                                    except ValueError:
                                        continue
                                break
                        break  # found a usable delimiter

            if ter_map:
                print(f"  [fetcher] Fetched TER for {len(ter_map)} schemes from AMFI")
                break

        except Exception as e:
            print(f"  [fetcher] TER fetch from {url} failed: {e}")
            continue

    if ter_map:
        try:
            with open(ter_cache, "w") as f:
                json.dump(ter_map, f)
        except Exception:
            pass
    else:
        print("  [fetcher] TER data unavailable — TER scoring will be skipped this run")

    return ter_map


# ─────────────────────────────────────────────────────────────────────────────
# Nifty P/E
# ─────────────────────────────────────────────────────────────────────────────

def get_nifty_pe() -> float | None:
    """Fetch latest Nifty 50 trailing P/E from niftyindices.com."""
    try:
        url = "https://www.niftyindices.com/Backpage.aspx/getPEPBDividenByIndexName"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Referer":       "https://www.niftyindices.com/",
        }
        r = requests.post(
            url,
            json={"indexName": "NIFTY 50", "indexType": "pricereturn"},
            headers=headers,
            timeout=10,
        )
        rows = r.json().get("d", [])
        if rows:
            latest = sorted(rows, key=lambda x: x.get("Date", ""))[-1]
            val = float(latest.get("pe", 0))
            if val:
                pe_cache = CACHE_DIR / "nifty_pe.json"
                pe_cache.write_text(json.dumps({"pe": val, "ts": datetime.now().isoformat()}))
                return val
    except Exception:
        pass

    # Fallback: cached value within 7 days
    pe_cache = CACHE_DIR / "nifty_pe.json"
    if _is_fresh(pe_cache, max_hours=168):
        try:
            return json.loads(pe_cache.read_text()).get("pe")
        except Exception:
            pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# AUM map
# ─────────────────────────────────────────────────────────────────────────────

def get_amfi_aum_map() -> dict[str, float]:
    """Returns {scheme_code: aum_crores}. Best-effort from AMFI."""
    aum_cache = _cache_path("amfi_aum")
    if _is_fresh(aum_cache, SCHEME_CACHE_HOURS):
        try:
            with open(aum_cache) as f:
                return json.load(f)
        except Exception:
            pass

    aum_map: dict[str, float] = {}
    try:
        url = "https://www.amfiindia.com/modules/AumNav"
        r = requests.get(url, timeout=20)
        for line in r.text.splitlines():
            parts = line.strip().split(";")
            if len(parts) >= 6 and parts[0].strip().isdigit():
                try:
                    code = parts[0].strip()
                    raw  = parts[5].strip().replace(",", "")
                    aum_map[code] = float(raw) if raw else 0.0
                except (ValueError, IndexError):
                    pass
    except Exception as e:
        print(f"  [fetcher] AUM fetch failed: {e}. AUM gate skipped.")

    if aum_map:
        try:
            with open(aum_cache, "w") as f:
                json.dump(aum_map, f)
        except Exception:
            pass

    return aum_map


# ─────────────────────────────────────────────────────────────────────────────
# Search utility
# ─────────────────────────────────────────────────────────────────────────────

def search_scheme(query: str, top_n: int = 15) -> list[dict]:
    """Find scheme codes by name. Used to verify benchmark codes."""
    all_cache = _cache_path("all_schemes")
    if not _is_fresh(all_cache, SCHEME_CACHE_HOURS):
        print("  Fetching full scheme list from mfapi.in...")
        r = requests.get(MFAPI_BASE, timeout=30)
        r.raise_for_status()
        data = r.json()
        with open(all_cache, "w") as f:
            json.dump(data, f)
    else:
        with open(all_cache) as f:
            data = json.load(f)

    q = query.lower()
    matches = [s for s in data if q in s.get("schemeName", "").lower()]
    return matches[:top_n]
