"""Yahoo Finance 시세 받기."""
import csv, io, json, time, urllib.request
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}

LOG = []
def get(url, tries=2, uas=({"User-Agent": "curl/8.5.0"}, UA)):
    last = None
    for ua in uas:
        for i in range(tries):
            t0 = time.time()
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=ua), timeout=20) as r:
                    return r.read().decode()
            except Exception as e:
                last = e
                LOG.append(f"{url[:70]} ua={ua['User-Agent'][:12]} {type(e).__name__}:{e} {time.time()-t0:.0f}s")
                time.sleep(2)
    raise last

def yahoo(sym, iv, rng=None):
    rng = rng or {"1wk": "since2014", "1d": "since2014", "1mo": "20y"}.get(iv, "max")
    span = (f"period1=1388534400&period2={int(time.time())}" if rng == "since2014"
            else f"period1={rng[1:]}&period2={int(time.time())}" if rng.startswith("p") else f"range={rng}")   # "p<유닉스초>" = 그날부터   # 2015년부터 차트 + 200/218일선 계산용 1년 여유
    j = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?{span}&interval={iv}"))
    res = j["chart"]["result"][0]
    off = (res.get("meta") or {}).get("gmtoffset", 0) or 0
    q = res["indicators"]["quote"][0]
    out = []
    for i, t in enumerate(res["timestamp"]):
        if q["close"][i] is None:
            continue
        out.append([t, *(round(q[k][i], 4) if q[k][i] is not None else q["close"][i] for k in ("open", "high", "low", "close"))])
    # Yahoo가 진행 중인 봉을 한 번 더 붙여 보내는 경우 → 직전 봉에 합침 (TradingView와 값 일치)
    if len(out) >= 2:
        a, b = out[-2], out[-1]
        da, db = datetime.fromtimestamp(a[0] + off, timezone.utc), datetime.fromtimestamp(b[0] + off, timezone.utc)
        same = ((iv == "1mo" and (da.year, da.month) == (db.year, db.month)) or
                (iv == "1wk" and (db - da).days < 7) or (iv == "1d" and da.date() == db.date()))
        if same:
            out[-2:] = [[a[0], a[1], max(a[2], b[2]), min(a[3], b[3]), b[4]]]
    # 마지막 봉 종가가 빈 값으로 오는 경우 → 실시간 시세(meta)로 채움 (하루 전 가격으로 되돌아가는 오류 방지)
    meta = res.get("meta", {})
    px, mt = meta.get("regularMarketPrice"), meta.get("regularMarketTime")
    if px and mt and out and mt > out[-1][0]:
        dl, dm = datetime.fromtimestamp(out[-1][0] + off, timezone.utc), datetime.fromtimestamp(mt + off, timezone.utc)
        same = ((iv == "1mo" and (dl.year, dl.month) == (dm.year, dm.month)) or
                (iv == "1wk" and (dm - dl).days < 7) or (iv == "1d" and dl.date() == dm.date()))
        if same:
            last = out[-1]; last[4] = round(px, 4); last[2] = max(last[2], px); last[3] = min(last[3], px)
        else:
            hi_ = meta.get("regularMarketDayHigh") or px; lo_ = meta.get("regularMarketDayLow") or px
            out.append([mt, round(px, 4), round(max(hi_, px), 4), round(min(lo_, px), 4), round(px, 4)])
    return out  # [unix, o, h, l, c]

