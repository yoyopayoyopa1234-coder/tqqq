"""폭락 가능성 페이지 참고 지표 → crash_data.json (VIX 일별 · 미국 고수익채 스프레드)"""
import json, os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(__file__))
from yahoo_data import yahoo, get

OUT = os.path.join(os.path.dirname(__file__), "..", "crash_data.json")
try: old = json.load(open(OUT))
except Exception: old = {}
out = dict(updated=datetime.now(timezone.utc).isoformat(timespec="minutes"), vix=old.get("vix"), hy=old.get("hy"))
try:
    r = yahoo("%5EVIX", "1d", "2y"); out["vix"] = [[x[0], x[4]] for x in r]; print("VIX", len(r), r[-1][4])
except Exception as e: print("VIX 실패", type(e).__name__, str(e)[:100])
try:
    rows = [l.split(",") for l in get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2").strip().splitlines()[1:]]
    rows = [[a, float(b)] for a, b in rows if b not in (".", "")][-520:]; out["hy"] = rows; print("HY", rows[-1])
except Exception as e: print("HY 실패", type(e).__name__, str(e)[:100])
json.dump(out, open(OUT, "w"), separators=(",", ":"))
