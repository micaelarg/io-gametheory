# /// script
# requires-python = ">=3.10"
# dependencies = ["requests>=2.31", "pandas>=2.1"]
# ///
"""Addresses → coordinates with OpenStreetMap Nominatim (free; usage policy: ≤ 1 request/second, cache results).

  uv run geocode.py "Carrer de Russafa 30, Valencia, Spain" "Avinguda del Port 120, Valencia, Spain" --out candidates.csv
  uv run geocode.py --csv sites.csv --address-col address --out candidates.csv     (keeps other columns, e.g. rent)

Always include city and country in the address. Check the result type/importance: a street-level match
(no house number) can be hundreds of meters off - the output flags it.
"""
from __future__ import annotations

import argparse
import json
import os
import time

import pandas as pd
import requests

CACHE = os.path.expanduser("~/.cache/io-gametheory/geocode.json")
UA = {"User-Agent": "io-gametheory-skill/0.1 (research script)"}


def geocode(q, cache):
    if q in cache:
        return cache[q]
    time.sleep(1.1)
    r = requests.get("https://nominatim.openstreetmap.org/search", params={"q": q, "format": "jsonv2", "limit": 1,
                     "addressdetails": 1}, headers=UA, timeout=60)
    r.raise_for_status()
    js = r.json()
    res = None
    if js:
        h = js[0]
        res = {"lat": float(h["lat"]), "lon": float(h["lon"]), "match": h.get("display_name", ""),
               "precision": "house" if "house_number" in h.get("address", {}) else h.get("addresstype", h.get("type", ""))}
    cache[q] = res
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("addresses", nargs="*")
    ap.add_argument("--csv"); ap.add_argument("--address-col", default="address")
    ap.add_argument("--out", default="geocoded.csv")
    a = ap.parse_args()
    df = pd.read_csv(a.csv) if a.csv else pd.DataFrame({a.address_col: a.addresses})
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    rows = []
    for q in df[a.address_col].astype(str):
        r = geocode(q, cache) or {"lat": None, "lon": None, "match": "NOT FOUND", "precision": ""}
        rows.append(r)
    json.dump(cache, open(CACHE, "w"))
    out = pd.concat([df.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    if "id" not in out.columns:
        out.insert(0, "id", [f"site{i+1}" for i in range(len(out))])
    out.to_csv(a.out, index=False)
    print(f"# Geocoded → `{a.out}`\n\n| id | address | lat | lon | precision |\n|---|---|---|---|---|")
    for _, r in out.iterrows():
        flag = "" if r["precision"] == "house" else " ⚠ not house-level"
        print(f"| {r['id']} | {r[a.address_col]} | {r['lat']} | {r['lon']} | {r['precision']}{flag} |")
    print("\n_Data © OpenStreetMap contributors (Nominatim). Verify each point on the map before using it._")


if __name__ == "__main__":
    main()
