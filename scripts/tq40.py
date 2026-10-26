"""TQQQ 40년 환산 주가 → tq40.json (하루 한 번).
나스닥100(^NDX) 일봉 × 3 − 조달금리(DFF×2) − 운용보수(ER 0.95%) − 스왑 스프레드(SS 1%×2).
2010-02-11 실제 TQQQ 상장일 가격에 맞춰 이어 붙임 (아기티큐 공개 수식과 같은 방식)."""
import csv, io, json, os, sys, time
from datetime import datetime, timezone, date
sys.path.insert(0, os.path.dirname(__file__))
from yahoo_data import get

FN = "tq40.json"; ER = 0.0095; SS = 0.01

def main():
    try:
        if time.time() - json.load(open(FN)).get("ts", 0) < 20 * 3600:
            print("tq40 최신 — 건너뜀"); return
    except Exception:
        pass
    j = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/%5ENDX?period1=489024000&period2={int(time.time())}&interval=1d"))
    r = j["chart"]["result"][0]
    ndx = [(datetime.fromtimestamp(t, timezone.utc).date(), c) for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if c]
    dff = {}
    for row in csv.reader(io.StringIO(get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFF"))):
        try: dff[date.fromisoformat(row[0])] = float(row[1])
        except Exception: pass
    j = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/TQQQ?period1=1262304000&period2={int(time.time())}&interval=1d&events=div,split"))
    r = j["chart"]["result"][0]
    tq = {datetime.fromtimestamp(t, timezone.utc).date(): a for t, a in zip(r["timestamp"], r["indicators"]["adjclose"][0]["adjclose"]) if a}
    dk = sorted(dff); last = dk[0]; k = 0
    syn = [1.0]
    for i in range(1, len(ndx)):
        d0, d1 = ndx[i - 1][0], ndx[i][0]; n = (d1 - d0).days
        while k + 1 < len(dk) and dk[k + 1] <= d0: k += 1
        rate = dff.get(d0, dff[dk[k]]) / 100
        ret = (ndx[i][1] / ndx[i - 1][1] - 1) * 3 - rate / 360 * n * 2 - ((1 + ER) ** (n / 365) - 1) - ((1 + SS) ** (n / 365) - 1) * 2
        syn.append(syn[-1] * (1 + ret))
    start = min(tq)
    idx = next(i for i, x in enumerate(ndx) if x[0] >= start)
    scale = tq[ndx[idx][0]] / syn[idx] if ndx[idx][0] in tq else tq[start] / syn[idx]
    out = {"ts": int(time.time()), "start": start.isoformat(), "er": ER, "ss": SS,
           "d": [x[0].isoformat() for x in ndx],
           "syn": [round(v * scale, 6) for v in syn],
           "real": [round(tq[x[0]], 4) if x[0] in tq else None for x in ndx],
           "ndx": [round(x[1], 2) for x in ndx]}
    json.dump(out, open(FN, "w"), separators=(",", ":"))
    print("tq40", len(ndx), out["d"][0], out["d"][-1])

if __name__ == "__main__":
    main()
