"""Mateo analysis: derived dataset = engine data/processed + ONE synthetic asset US_MKT_XEN.

US_MKT_XEN = US market ex-energy proxy: cap-weighted mix of the 11 Ken French industries other than
Enrgy, using the KF cap shares of lookthrough_us_mkt.parquet. KF "Average Firm Size" at month t is the
size at the end of month t-1, so the share labelled t weights the return of month t (no look-ahead).
    r_xen(t) = sum_{i != Enrgy} s_i(t) r_i(t) / sum_{i != Enrgy} s_i(t)
Same formula in USD and CAD (FX factor is common to all USD assets).
The engine's data/ is NOT modified: everything is written to analysis/mateo/data_ext/ and loaded via
ALPHAFORGE_BT_DATA. SIMULATION ONLY.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
SRC = HERE.parent.parent / "data" / "processed"
DST = HERE / "data_ext"


def main():
    DST.mkdir(exist_ok=True)
    for f in SRC.iterdir():
        if f.is_file():
            shutil.copy2(f, DST / f.name)
    long = pd.read_parquet(SRC / "monthly_returns.parquet")
    long["date"] = pd.to_datetime(long["date"])
    lt = pd.read_parquet(SRC / "lookthrough_us_mkt.parquet")
    lt = lt.set_index(pd.to_datetime(lt["date"])).drop(columns="date")
    inds = [c for c in lt.columns if c != "US_IND_ENRGY"]
    out = {}
    for col in ("return_usd", "return_cad"):
        piv = long[long.asset_id.isin(inds)].pivot(index="date", columns="asset_id", values=col)[inds]
        sh = lt[inds].reindex(piv.index)
        ok = piv.notna().all(axis=1) & sh.notna().all(axis=1)
        out[col] = (piv[ok] * sh[ok]).sum(axis=1) / sh[ok].sum(axis=1)
    df = pd.DataFrame(out).reset_index().rename(columns={"index": "date"})
    df["asset_id"] = "US_MKT_XEN"
    df["source"] = "derived: KF 12 industries ex-Enrgy, cap-weighted with KF shares (analysis/mateo/build_ext_data.py)"
    df["flag"] = "synthetic_ex_energy"
    df = df[long.columns]
    new = pd.concat([long, df], ignore_index=True)
    new.to_parquet(DST / "monthly_returns.parquet", index=False)
    a = pd.read_csv(SRC / "assets.csv", keep_default_na=False)
    last = lt.iloc[-1]
    tech = last["US_IND_BUSEQ"] / (1 - last["US_IND_ENRGY"])
    row = {c: "" for c in a.columns}
    row.update(asset_id="US_MKT_XEN", name="US market ex-energy (KF 11 industries, cap-weighted) - ESG sector-exclusion PROXY",
               asset_class="equity_us", currency="USD", start=str(df.date.min().date()), end=str(df.date.max().date()),
               n_months=len(df), tags="equity;broad_market;esg_proxy_ex_fossil",
               exposures=f"tech={tech:.4f};energy=0.0", universe_tickers="ESGV(approx: ESGV also excludes other sectors);SPY ex XOM",
               proxy_for_ticker="", maturity_years="",
               notes="Sector exclusion of KF Enrgy (SIC oil, gas & coal) only. NOT an ESG score; pipelines (SIC 4922) stay in Utils.")
    a = pd.concat([a, pd.DataFrame([row])], ignore_index=True)
    a.to_csv(DST / "assets.csv", index=False)
    v = json.loads((SRC / "data_version.json").read_text())
    h = hashlib.sha256((DST / "monthly_returns.parquet").read_bytes() + (DST / "assets.csv").read_bytes()).hexdigest()[:16]
    v["source_data_sha256"] = v["data_sha256"]
    v["data_sha256"] = "mateo_ext_" + h
    v["mateo_extension"] = "US_MKT_XEN added by analysis/mateo/build_ext_data.py; engine data/processed unchanged"
    (DST / "data_version.json").write_text(json.dumps(v, indent=1))
    print("ok", v["data_sha256"], "from", v["source_data_sha256"], len(df), "rows")
    # sanity: correlation with US_MKT
    m = long[long.asset_id == "US_MKT"].set_index("date")["return_usd"]
    x = df.set_index("date")["return_usd"]
    print("corr US_MKT~XEN", round(m.corr(x), 4), "ann diff", round(((1 + x).prod() ** (12 / len(x)) - (1 + m.reindex(x.index)).prod() ** (12 / len(x))), 4))


if __name__ == "__main__":
    main()
