"""백테스트용 일봉(배당 반영 수정종가, 2010년~) → bt_data.json. 하루 한 번만 갱신."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from yahoo_data import get

FN = "bt_data.json"
SYMS = ["SPY", "QQQ", "QLD", "TQQQ", "SOXL"]

def main():
    if os.path.exists(FN) and time.time() - os.path.getmtime(FN) < 20 * 3600:
        try:
            if time.time() - json.load(open(FN)).get("ts", 0) < 20 * 3600:
                print("bt_data 최신 — 건너뜀"); return
        except Exception:
            pass
    out = {"ts": int(time.time()), "adj": {}}
    for s in SYMS:
        j = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?period1=1262304000&period2={int(time.time())}&interval=1d&events=div,split"))
        r = j["chart"]["result"][0]
        adj = r["indicators"]["adjclose"][0]["adjclose"]
        q = r["indicators"]["quote"][0]
        out["adj"][s] = [[t, round(a, 4), round(h, 4) if h else None, round(l, 4) if l else None, round(c, 4)]
                         for t, a, h, l, c in zip(r["timestamp"], adj, q["high"], q["low"], q["close"]) if a and c]
        print(s, len(out["adj"][s]))
    json.dump(out, open(FN, "w"), separators=(",", ":"))

if __name__ == "__main__":
    main()
