"""FedWatch 대체 → fedwatch.json (매 실행 · 15분마다).

CME FedWatch 사이트는 막혀 있어서 같은 원재료와 주변 신호로 대신 본다.
  1. 연방기금 선물(30일물, CBOT ZQ) 가격 → 달마다 시장이 예상하는 평균 기준금리 → 다음 FOMC 인하·동결·인상 확률 (FedWatch와 같은 계산법)
  2. 뉴스: 'FedWatch' · '페드워치' · 'rate cut odds' 기사 수와 제목 속 확률 숫자 (Google 뉴스 RSS)
기록은 실행마다 쌓아 두고(최근 30일) 페이지가 추이를 그린다.
"""
import json, os, re, sys, time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta, date
from email.utils import parsedate_to_datetime
from urllib.parse import quote
sys.path.insert(0, os.path.dirname(__file__))
from yahoo_data import get

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "fedwatch.json")
# FOMC 결정일(둘째 날). 2027년은 연준 발표 일정 기준 — 바뀌면 여기만 고치면 됨
FOMC = ["2026-10-28", "2026-12-09", "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-16", "2027-07-28", "2027-09-22", "2027-10-27", "2027-12-08"]
MC = "FGHJKMNQUVXZ"
QUERIES = [("en", "FedWatch"), ("en", "\"rate cut\" odds Fed"), ("en", "fed funds futures"), ("ko", "페드워치"), ("ko", "금리 인하 확률 연준")]


def yahoo_price(sym):
    try:
        j = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(sym)}?range=5d&interval=1d"))
        m = j["chart"]["result"][0]["meta"]
        p = m.get("regularMarketPrice")
        return (float(p), m.get("regularMarketTime")) if p else (None, None)
    except Exception as e:
        print("yahoo 실패", sym, type(e).__name__, str(e)[:80]); return None, None


def futures(now):
    """앞으로 13개월 연방기금 선물 → 달별 예상 평균 금리"""
    out = []
    y, m = now.year, now.month
    for k in range(13):
        yy, mm = y + (m - 1 + k) // 12, (m - 1 + k) % 12 + 1
        sym = f"ZQ{MC[mm - 1]}{yy % 100:02d}.CBT"
        p, t = yahoo_price(sym)
        if p is None and k == 0:
            p, t = yahoo_price("ZQ=F")
        out.append(dict(month=f"{yy}-{mm:02d}", sym=sym, price=p, rate=None if p is None else round(100 - p, 4), t=t))
    return out


def meetings(fut, effr):
    """FedWatch 방식: 회의가 있는 달의 선물 = 회의 전 금리 × 회의 전 일수 + 회의 후 금리 × 나머지 일수"""
    R = {f["month"]: f["rate"] for f in fut if f["rate"] is not None}
    res = []; pre = effr
    for ds in FOMC:
        d = date.fromisoformat(ds)
        if d < datetime.now(timezone.utc).date():
            continue
        mk = f"{d.year}-{d.month:02d}"
        nxt = date(d.year + d.month // 12, d.month % 12 + 1, 1); nk = f"{nxt.year}-{nxt.month:02d}"
        days = (nxt - date(d.year, d.month, 1)).days
        meet_next = any(x.startswith(nk) for x in FOMC)
        post = None
        if not meet_next and nk in R:
            post = R[nk]
        elif mk in R and pre is not None and days - d.day > 0:
            post = (R[mk] * days - pre * d.day) / (days - d.day)
        if post is None or pre is None:
            res.append(dict(date=ds, pre=pre, post=None)); continue
        ch = post - pre
        steps = ch / 0.25
        # 0.25%p 한 번 = 100%. 0.4번이면 인하 40%·동결 60%, 1.3번이면 0.25 인하 70%·0.5 인하 30%
        a = abs(steps); lo = int(a); fr = a - lo
        big = lo >= 1
        res.append(dict(date=ds, pre=round(pre, 3), post=round(post, 3), change=round(ch, 3),
                        cut=round(min(1.0, -steps) * 100, 1) if steps < 0 else 0.0,
                        hike=round(min(1.0, steps) * 100, 1) if steps > 0 else 0.0,
                        big=round(fr * 100, 1) if big else 0.0,
                        cum=round(post - effr, 3)))
        pre = post
    return res


def kalshi():
    """Kalshi 'Fed decision' 예측시장 — 돈을 건 사람들의 확률 (회의별 인하·동결·인상)"""
    out = []
    for st in ("KXFEDDECISION", "FEDDECISION"):
        try:
            j = json.loads(get(f"https://api.elections.kalshi.com/trade-api/v2/events?series_ticker={st}&status=open&with_nested_markets=true&limit=10"))
        except Exception as e:
            print("kalshi 실패", st, type(e).__name__, str(e)[:80]); continue
        for ev in j.get("events", []):
            mk = []
            for m in ev.get("markets", []):
                p = m.get("last_price") or m.get("yes_bid")
                if p is None: continue
                mk.append(dict(name=m.get("yes_sub_title") or m.get("subtitle") or m.get("ticker"), p=float(p), vol=m.get("volume")))
            if mk:
                out.append(dict(title=ev.get("title"), ticker=ev.get("event_ticker"), close=ev.get("strike_date") or ev.get("close_time"), markets=mk))
        print("kalshi", st, len(out), [(e["title"], e["markets"][:4]) for e in out[:2]])
        if out: break
    return out


def polymarket():
    out = []
    for url in ("https://gamma-api.polymarket.com/events?closed=false&limit=20&tag_slug=fed-rates",
                "https://gamma-api.polymarket.com/public-search?q=fed%20decision&limit_per_type=10"):
        try:
            j = json.loads(get(url))
        except Exception as e:
            print("polymarket 실패", url[30:70], type(e).__name__, str(e)[:80]); continue
        evs = j if isinstance(j, list) else j.get("events", [])
        for ev in evs:
            if ev.get("closed") or "fed" not in (ev.get("title") or "").lower(): continue
            mk = []
            for m in ev.get("markets", []):
                if m.get("closed"): continue
                try: p = float(json.loads(m.get("outcomePrices") or "[]")[0]) * 100
                except Exception: continue
                mk.append(dict(name=m.get("groupItemTitle") or m.get("question"), p=round(p, 1), vol=m.get("volume")))
            if mk:
                out.append(dict(title=ev.get("title"), slug=ev.get("slug"), close=ev.get("endDate"), markets=mk))
        print("polymarket", len(out), [(e["title"], e["markets"][:4]) for e in out[:3]])
        if out: break
    return out


PCT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s?%")
KW = {"cut": ["cut", "cuts", "easing", "lower rates", "reduction", "인하"], "hold": ["hold", "pause", "unchanged", "steady", "동결"], "hike": ["hike", "raise", "increase", "tighten", "인상"]}


def news():
    items = {}
    for lang, q in QUERIES:
        url = (f"https://news.google.com/rss/search?q={quote(q)}+when:7d&hl=en-US&gl=US&ceid=US:en" if lang == "en"
               else f"https://news.google.com/rss/search?q={quote(q)}+when:7d&hl=ko&gl=KR&ceid=KR:ko")
        try:
            root = ET.fromstring(get(url))
        except Exception as e:
            print("뉴스 실패", q, type(e).__name__, str(e)[:80]); continue
        n = 0
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip(); link = it.findtext("link") or ""
            try: ts = parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc)
            except Exception: continue
            src = it.find("source"); src = src.text if src is not None else ""
            key = re.sub(r"\s+-\s+[^-]+$", "", title).lower()[:90]
            if key in items: items[key]["q"].add(q); continue
            items[key] = dict(title=title, link=link, ts=ts, src=src, lang=lang, q={q}); n += 1
        print(f"뉴스 '{q}': {n}건")
    out = []
    for v in items.values():
        t = v["title"].lower(); probs = []
        for m in PCT.finditer(v["title"]):
            val = float(m.group(1))
            if val > 100: continue
            win = t[max(0, m.start() - 60): m.end() + 60]
            kind = None; best = 999
            for k, ws in KW.items():
                for w in ws:
                    j = win.find(w)
                    if j >= 0 and abs(j - 60) < best: best = abs(j - 60); kind = k
            if kind and any(w in t for w in ("fedwatch", "페드워치", "odds", "probability", "chance", "확률", "가능성", "price in", "priced", "bets", "futures", "traders")):
                probs.append([kind, val])
        out.append(dict(title=v["title"], link=v["link"], ts=v["ts"].isoformat(timespec="minutes"), src=v["src"], lang=v["lang"],
                        fw="fedwatch" in t or "페드워치" in t, probs=probs))
    out.sort(key=lambda x: x["ts"], reverse=True)
    return out


def main():
    now = datetime.now(timezone.utc)
    try: old = json.load(open(OUT))
    except Exception: old = {}
    effr = None
    try:
        raw = json.load(open(os.path.join(ROOT, "crash_raw.json")))
        effr = raw["series"]["DFF"][-1][1]
    except Exception as e:
        print("EFFR 없음", e)
    fut = futures(now)
    got = sum(1 for f in fut if f["rate"] is not None)
    print(f"선물 {got}/13개", [(f["month"], f["rate"]) for f in fut[:4]])
    if got == 0 and old.get("futures"):
        fut = old["futures"]; print("선물 실패 — 이전 값 유지")
    mt = meetings(fut, effr) if effr is not None else []
    nw = news()
    if not nw and old.get("news"):
        nw = old["news"]
    ks = kalshi() or old.get("kalshi", [])
    pm = polymarket() or old.get("poly", [])
    def cnt(h, fw_only=False):
        lim = now - timedelta(hours=h)
        return sum(1 for x in nw if datetime.fromisoformat(x["ts"]) >= lim and (x["fw"] or not fw_only))
    recent_probs = [p for x in nw if datetime.fromisoformat(x["ts"]) >= now - timedelta(hours=72) for p in x["probs"]]
    def med(k):
        v = sorted(p[1] for p in recent_probs if p[0] == k)
        return None if not v else v[len(v) // 2]
    snap = dict(t=now.isoformat(timespec="minutes"), n24=cnt(24), fw24=cnt(24, True), n7d=len(nw),
                cut=mt[0].get("cut") if mt else None, cum=next((m.get("cum") for m in mt if m["date"] >= "2026-12-31"), None))
    hist = [h for h in old.get("hist", []) if datetime.fromisoformat(h["t"]) >= now - timedelta(days=30)] + [snap]
    json.dump(dict(ts=int(now.timestamp()), effr=effr, futures=fut, meetings=mt, kalshi=ks, poly=pm, news=nw[:40], counts=dict(n24=snap["n24"], fw24=snap["fw24"], n7d=len(nw), fw7d=sum(1 for x in nw if x["fw"])),
                   news_probs=dict(cut=med("cut"), hold=med("hold"), hike=med("hike"), n=len(recent_probs)), hist=hist[-3000:]),
              open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
    print("fedwatch", "다음 회의", mt[0] if mt else None, "뉴스 24h", snap["n24"], "FedWatch 언급", snap["fw24"])


if __name__ == "__main__":
    main()
