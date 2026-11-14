"""Short-duration FI variant (50% bonds / 50% cash) across CAD77, CAD71, USD46 -> envelope for 'Tres faible'. Run like calib.py."""
import os, pathlib
_HERE = pathlib.Path(os.environ.get("CALIB_DIR", pathlib.Path.cwd()))
import importlib.util, pandas as pd
spec = importlib.util.spec_from_file_location("calib", str(_HERE / "calib.py")); C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)
C.EQ = [0, 5, 10, 15, 20, 25]
F = {"CAD77_hc": (["CA_EQ","US_MKT","CA_GOV_10Y","CA_TBILL"], {"CA_EQ":.5,"US_MKT":.5}, {"CA_GOV_10Y":.5,"CA_TBILL":.5}, "1977-01", "CAD"),
     "CAD71_hc": (["US_MKT","CA_GOV_10Y","CA_TBILL"], {"US_MKT":1.}, {"CA_GOV_10Y":.5,"CA_TBILL":.5}, "1971-02", "CAD"),
     "USD46_hc": (["US_MKT","UST_5Y","UST_TBILL"], {"US_MKT":1.}, {"UST_5Y":.5,"UST_TBILL":.5}, "1946-01", "USD")}
rows = []
for k,(a,eq,fi,s,cur) in F.items(): rows += C.run_family(k,a,eq,fi,s,cur)[0]
df = pd.DataFrame(rows); df.to_csv(C.OUT+"halfcash_env.csv", index=False)
print(df[["mix","eq","vol","mdd","mdd_real","uw_max","cvar95_12m","worst12","y2022","ploss_1y","ploss_3y","ploss_real_1y","ploss_real_5y"]].round(3).to_string())
