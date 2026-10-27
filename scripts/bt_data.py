"""백테스트용 일봉(배당 반영 수정종가, 2010년~) → bt_data.json.
하루 한 번 갱신하되, 직전 갱신이 미국 장중(마감 전)이었으면 장 마감 뒤 첫 실행에서 한 번 더 받아 마지막 봉을 확정 종가로 바꾼다."""
import json, os, sys, time
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(__file__))
from yahoo_data import get
from tq40 import us_close_utc, day

FN = "bt_data.json"
SYMS = ["SPY", "QQQ", "QLD", "TQQQ", "SOXL"]

def main():
    now = time.time()
    try:
        old = json.load(open(FN)); ts = old.get("ts", 0); last = day(old["adj"]["QQQ"][-1][0])
        fetched_partial = datetime.fromtimestamp(ts, timezone.utc) < us_close_utc(last)   # 장중에 받은 봉
        closed_since = datetime.fromtimestamp(now, timezone.utc) >= us_close_utc(last)
        if now - ts < 20 * 3600 and not (fetched_partial and closed_since):
            print("bt_data 최신 — 건너뜀"); return
    except Exception:
        pass
    out = {"ts": int(now), "adj": {}}
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
