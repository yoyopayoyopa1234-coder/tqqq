"""빅테크 Vix Fix 저점 진입 / 고점 청산 20년 백테스트 → backtest.json
규칙: 해당 봉 종가 기준. 저점 분류(녹색 신호 또는 WVF 100봉 상위 20%)면 전액 매수, 고점 분류(WVF 100봉 하위 20%)면 전량 매도 후 현금(이자 0%).
가격은 분할 조정 종가(배당 제외), 수수료·세금 제외. 비교: 같은 기간 매수 후 보유.
"""
import json, os, sys, math
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.dirname(__file__))
from yahoo_data import yahoo
from indicators import vixfix

TICKERS = [("NVDA", "엔비디아"), ("AAPL", "애플"), ("GOOGL", "구글"), ("MSFT", "마이크로소프트"), ("AMZN", "아마존"), ("TSM", "TSMC")]
YEARS = 20
START = datetime.now(timezone.utc) - timedelta(days=int(365.25 * YEARS))

def zones(r):
    h, l, c = [x[2] for x in r], [x[3] for x in r], [x[4] for x in r]
    w, up, rh, sig = vixfix(h, l, c)
    z = []
    for i in range(len(r)):
        if i < 43: z.append(None); continue
        hist = w[max(0, i - 99):i + 1]
        p = sum(1 for x in hist if x <= w[i]) / len(hist) * 100
        z.append("low" if (sig[i] or p >= 80) else ("high" if p <= 20 else "mid"))
    return z

def stats(eq, dates):
    yrs = (dates[-1] - dates[0]).days / 365.25
    cagr = (eq[-1] / eq[0]) ** (1 / yrs) - 1 if yrs > 0 else 0
    pk, mdd = eq[0], 0
    for v in eq: pk = max(pk, v); mdd = min(mdd, v / pk - 1)
    return round(cagr * 100, 2), round(mdd * 100, 1), round(eq[-1] / eq[0], 2)

def run(r):
    z = zones(r)
    dates = [datetime.fromtimestamp(x[0], timezone.utc) for x in r]
    s = next(i for i, d in enumerate(dates) if d >= START)
    c = [x[4] for x in r]
    pos, cash, sh, eq, trades, entry, inmkt = 0, 1.0, 0.0, [], [], None, 0
    for i in range(s, len(r)):
        if pos == 0 and z[i] == "low":
            sh, cash, pos, entry = cash / c[i], 0.0, 1, (dates[i], c[i])
        elif pos == 1 and z[i] == "high":
            cash, sh, pos = sh * c[i], 0.0, 0
            trades.append(c[i] / entry[1] - 1)
        eq.append(cash + sh * c[i]); inmkt += pos
    open_ret = (c[-1] / entry[1] - 1) if pos else None
    sc, sm, sx = stats(eq, dates[s:])
    bh = [c[i] / c[s] for i in range(s, len(r))]
    bc, bm, bx = stats(bh, dates[s:])
    wins = sum(1 for t in trades if t > 0)
    return {"cagr": sc, "mdd": sm, "mult": sx, "bh_cagr": bc, "bh_mdd": bm, "bh_mult": bx,
            "trades": len(trades), "win": round(wins / len(trades) * 100) if trades else None,
            "avg_trade": round(sum(trades) / len(trades) * 100, 1) if trades else None,
            "in_mkt": round(inmkt / (len(r) - s) * 100), "holding": pos == 1,
            "open_ret": round(open_ret * 100, 1) if open_ret is not None else None,
            "start": dates[s].strftime("%Y-%m-%d"), "end": dates[-1].strftime("%Y-%m-%d"),
            "eq": [round(v, 4) for v in eq[:: max(1, len(eq) // 120)]], "bh": [round(v, 4) for v in bh[:: max(1, len(bh) // 120)]]}

def main():
    out = {"updated": datetime.now(timezone.utc).isoformat(timespec="minutes"), "years": YEARS, "tf": {}}
    for iv in ("1d", "1wk", "1mo"):
        rows = []
        for sym, name in TICKERS:
            try:
                r = yahoo(sym, iv, "max")
                res = run(r); res.update(sym=sym, name=name); rows.append(res)
                print(iv, sym, res["cagr"], res["bh_cagr"], res["mdd"], res["bh_mdd"], res["trades"], res["in_mkt"])
            except Exception as e:
                rows.append({"sym": sym, "name": name, "error": str(e)[:80]}); print("FAIL", iv, sym, e)
        ok = [x for x in rows if "cagr" in x]
        # 6종목 동일 비중(종목별 전략 결과 평균)
        if ok:
            out.setdefault("avg", {})[iv] = {k: round(sum(x[k] for x in ok) / len(ok), 2) for k in ("cagr", "bh_cagr", "mdd", "bh_mdd", "in_mkt")}
        out["tf"][iv] = rows
    json.dump(out, open("backtest.json", "w"), ensure_ascii=False, separators=(",", ":"))

if __name__ == "__main__":
    main()
