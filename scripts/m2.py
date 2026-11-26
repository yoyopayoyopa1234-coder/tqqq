"""Global M2 (달러 환산, 일별) → m2_data.json
각국 통화량 최신 발표값(월별, FRED·ECB) × 일별 환율(Yahoo, 실패 시 FRED)을 더한다. 6시간마다 다시 받음."""
import csv, io, json, os, sys, time
from datetime import date, datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(__file__))
from yahoo_data import yahoo, get

OUT = os.path.join(os.path.dirname(__file__), "..", "m2_data.json")
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
# (나라, 통화량 후보 [(종류, 코드, 곱수)], 환율 (야후, FRED, 뒤집기), 달러 환산 허용 범위 조 달러)
C = [("미국", [("fred", "M2SL", 1e9), ("fred", "WM2NS", 1e9)], None, (15, 35)),
     ("유로존", [("ecb", "BSI/M.U2.Y.V.M20.X.1.U2.2300.Z01.E", 1e6), ("fred", "MABMM301EZM189S", 1)], ("EURUSD=X", "DEXUSEU", False), (8, 30)),
     ("중국", [("fred", "MYAGM2CNM189N", 1), ("fred", "MABMM301CNM189S", 1), ("fred", "MABMM301CNM189N", 1)], ("CNY=X", "DEXCHUS", True), (20, 80)),
     ("일본", [("fred", "MABMM301JPM189S", 1), ("fred", "MYAGM2JPM189S", 1), ("fred", "MABMM301JPM189N", 1)], ("JPY=X", "DEXJPUS", True), (4, 20)),
     ("영국", [("fred", "MABMM301GBM189S", 1), ("fred", "MABMM301GBM189N", 1)], ("GBPUSD=X", "DEXUSUK", False), (1.5, 8))]
START = date(2014, 1, 1)

def fred(code):
    out = []
    for r in list(csv.reader(io.StringIO(get(FRED + code))))[1:]:
        try: out.append((date.fromisoformat(r[0]), float(r[1])))
        except Exception: pass
    return out

def ecb(key):
    rows = list(csv.DictReader(io.StringIO(get(f"https://data-api.ecb.europa.eu/service/data/{key}?format=csvdata&startPeriod=2013-01"))))
    return [(date.fromisoformat(r["TIME_PERIOD"] + "-01"), float(r["OBS_VALUE"])) for r in rows if r.get("OBS_VALUE")]

def ffill(obs, days):
    obs = sorted(obs); out, j, v = [], 0, None
    for d in days:
        while j < len(obs) and obs[j][0] <= d: v = obs[j][1]; j += 1
        out.append(v)
    return out

def main():
    try: old = json.load(open(OUT))
    except Exception: old = {}
    now = datetime.now(timezone.utc)
    if old.get("m2", {}).get("rows") and old.get("ts") and time.time() - old["ts"] < 6 * 3600 and "--force" not in sys.argv:
        print("캐시 사용"); return
    today = now.date(); days = []; d = START
    while d <= today:
        if d.weekday() < 5: days.append(d)
        d += timedelta(days=1)
    diag, used, notes, total = [], [], [], [0.0] * len(days)
    for name, cands, fx, (lo, hi) in C:
        ser = None
        for kind, code, mul in cands:
            try:
                obs = [(a, b * mul) for a, b in (fred(code) if kind == "fred" else ecb(code))]
                last = obs[-1]; fresh = (today - last[0]).days <= 200
                diag.append(f"{name} {code}: {len(obs)}개 · 마지막 {last[0]} {last[1]:.4g} · {'사용 가능' if fresh else '오래됨'}")
                if fresh and not ser: ser = (code, obs)
            except Exception as e: diag.append(f"{name} {code}: 실패 {type(e).__name__} {str(e)[:80]}")
        if not ser: notes.append(f"{name} 제외(최신 자료 없음)"); continue
        if fx:
            ysym, fcode, inv = fx; rate = None
            try: rate = [(datetime.fromtimestamp(r[0], timezone.utc).date(), r[4]) for r in yahoo(ysym, "1d", "p1380000000")]
            except Exception as e: diag.append(f"{name} 환율 야후 실패 {type(e).__name__}")
            if not rate or len(rate) < 500:
                try: rate = fred(fcode)
                except Exception as e: diag.append(f"{name} 환율 FRED 실패 {type(e).__name__}"); rate = None
            if not rate: notes.append(f"{name} 제외(환율 없음)"); continue
            fxs = [(1 / v if inv else v) if v else None for v in ffill(rate, days)]
        else: fxs = [1.0] * len(days)
        m = ffill(ser[1], days)
        usd = [a * b / 1e12 if a is not None and b is not None else None for a, b in zip(m, fxs)]
        lastv = next((v for v in reversed(usd) if v is not None), None)
        if lastv is None or not lo <= lastv <= hi:
            diag.append(f"{name} {ser[0]}: 달러 환산 {lastv} 조 — 범위({lo}~{hi}) 밖이라 제외"); notes.append(f"{name} 제외(값 이상)"); continue
        if any(v is None for v in usd[20:]):
            first = next(v for v in usd if v is not None); usd = [first if v is None else v for v in usd]
        total = [t + (v or 0) for t, v in zip(total, usd)]
        used.append(name); diag.append(f"{name} 채택 {ser[0]}: 최근 {lastv:.2f}조 달러 (자료 {ser[1][-1][0]:%Y-%m})")
    for x in diag: print(x)
    if "미국" not in used or len(used) < 2:
        print("나라 수 부족 — 기존 파일 유지"); old["diag"] = diag
        if old.get("m2"): json.dump(old, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
        else: json.dump(dict(ts=0, diag=diag), open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
        return
    rows = [[d.isoformat(), round(v, 3)] for d, v in zip(days, total)]
    json.dump(dict(ts=int(time.time()), updated=now.isoformat(timespec="minutes"), m2=dict(rows=rows, countries=used, notes=notes), diag=diag),
              open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
    print("Global M2", rows[-1], used, notes)

if __name__ == "__main__":
    main()
