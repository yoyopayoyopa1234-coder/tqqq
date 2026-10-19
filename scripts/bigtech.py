"""빅테크 7종목 Williams Vix Fix(22/20/2/50/0.85) → 저점/중간점/고점 분류 → bigtech.json

분류 기준 (봉 단위별):
  저점  = Vix Fix 녹색 신호(WVF ≥ BB상단 또는 ≥ RangeHigh) 이거나 WVF가 최근 100봉 중 상위 20%  → 공포·투매권
  고점  = WVF가 최근 100봉 중 하위 20%  → 공포가 사라진 안심·과열권 (가격이 최근 고점 근처)
  중간점 = 그 사이
"""
import json, os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(__file__))
from yahoo_data import yahoo
from indicators import vixfix

TICKERS = [("NVDA", "엔비디아"), ("AAPL", "애플"), ("GOOGL", "구글"), ("MSFT", "마이크로소프트"),
           ("AMZN", "아마존"), ("TSM", "TSMC"), ("SPCX", "스페이스X")]
TFS = [("1d", "일봉"), ("1wk", "주봉"), ("1mo", "월봉")]
LOOK = 100
MIN_BARS = 44          # 22봉 최고 종가 + 20봉 BB가 최소한 계산되는 길이

def classify(r):
    h, l, c = [x[2] for x in r], [x[3] for x in r], [x[4] for x in r]
    w, up, rh, sig = vixfix(h, l, c)
    cur = w[-1]; hist = w[-LOOK:]
    pctl = sum(1 for x in hist if x <= cur) / len(hist) * 100
    hc22 = max(c[-22:])
    last_green = next((i for i in range(len(sig) - 1, -1, -1) if sig[i]), None)
    if sig[-1] or pctl >= 80: zone = "low"
    elif pctl <= 20: zone = "high"
    else: zone = "mid"
    return {
        "price": round(c[-1], 2), "chg": round((c[-1] / c[-2] - 1) * 100, 2),
        "wvf": round(cur, 2), "rh": round(rh[-1], 2), "bbup": round(up[-1], 2) if up[-1] is not None else None,
        "ratio": round(cur / rh[-1] * 100, 1) if rh[-1] else None, "pctl": round(pctl), "sig": bool(sig[-1]),
        "from_high": round((c[-1] / hc22 - 1) * 100, 2), "zone": zone, "bars": len(r),
        "last_green": datetime.fromtimestamp(r[last_green][0], timezone.utc).strftime("%Y-%m-%d") if last_green is not None else None,
        "greens_recent": sum(sig[-20:]),
    }

def main():
    out = {"updated": datetime.now(timezone.utc).isoformat(timespec="minutes"), "tf": {}}
    for iv, _ in TFS:
        out["tf"][iv] = []
        for sym, name in TICKERS:
            row = {"sym": sym, "name": name}
            try:
                r = yahoo(sym, iv, {"1d": "2y", "1wk": "10y", "1mo": "20y"}[iv])
                if len(r) < MIN_BARS:
                    row["note"] = f"상장 후 {len(r)}봉 — {dict(TFS)[iv]} 계산 불가"
                else:
                    row.update(classify(r))
            except Exception as e:
                row["note"] = f"시세 오류: {str(e)[:60]}"
            out["tf"][iv].append(row)
            print(iv, sym, row.get("zone"), row.get("wvf"), row.get("pctl"), row.get("note", ""))
    json.dump(out, open("bigtech.json", "w"), ensure_ascii=False, separators=(",", ":"))

if __name__ == "__main__":
    main()
