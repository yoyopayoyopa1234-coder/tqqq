"""FedWatch 주변 반응 → fedwatch.json (매 실행 · 15분마다).

CME FedWatch 사이트는 막혀 있어서 그 '주변'을 센다 (Google 뉴스 RSS, 최근 7일):
  1. 언급 수: 'FedWatch' · '페드워치' · 'rate cut odds' 등 검색어별 24시간/7일 기사 수 (같은 기사 여러 매체는 한 번)
  2. 반응 뉴스: 최근 기사 제목 · 매체 · 시각
  3. 떠도는 수치: 제목 속 '확률·odds·FedWatch'와 함께 나온 퍼센트를 인하/동결/인상으로 분류(어느 달 회의인지도 표시)
기록은 실행마다 쌓아 두고(최근 30일) 페이지가 추이를 그린다.
"""
import json, os, re, sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote
sys.path.insert(0, os.path.dirname(__file__))
from yahoo_data import get

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "fedwatch.json")
QUERIES = [("en", "FedWatch"), ("en", "\"rate cut\" odds Fed"), ("en", "fed funds futures"), ("ko", "페드워치"), ("ko", "금리 인하 확률 연준")]
DIAG = []
def note(*a):
    m = " ".join(str(x) for x in a); print(m); DIAG.append(m[:300])
MON = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


MRE = re.compile(r"\b(january|february|march|april|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)\b|(\d{1,2})월")


def kind_near(t, pos):
    """달 이름 바로 뒤(20자 안)에 나오는 말: 'december hike', '12월 금리 인상', 'december rate cut'"""
    best = None
    for k, ws in KW.items():
        for w in ws:
            for m in re.finditer(re.escape(w), t):
                dd = m.start() - pos
                if 0 < dd <= 20 and (best is None or dd < best[0]): best = (dd, k)
    return best[1] if best else None


def month_of(t, pos, kind):
    """퍼센트 숫자(pos) 근처(40자 안) 달 이름 — 그 달 옆의 말(인하/동결/인상)이 숫자의 종류와 같을 때만 붙임"""
    best = None
    for m in MRE.finditer(t):
        mo = MON[m.group(1)[:3]] if m.group(1) else int(m.group(2))
        if not 1 <= mo <= 12 or kind_near(t, m.start()) != kind: continue
        dist = abs(m.start() - pos)
        if dist <= 40 and (best is None or dist < best[0]): best = (dist, mo)
    return best[1] if best else None


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
            note("뉴스 실패", q, type(e).__name__, str(e)[:80]); continue
        n = 0
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip(); link = it.findtext("link") or ""
            try: ts = parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc)
            except Exception: continue
            src = it.find("source"); src = src.text if src is not None else ""
            key = re.sub(r"\s+-\s+[^-]+$", "", title).lower()[:90]
            if key in items: items[key]["q"].add(q); continue
            if ts < datetime.now(timezone.utc) - timedelta(days=8): continue
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
                probs.append([kind, val, month_of(t, m.start(), kind)])
        out.append(dict(title=v["title"], link=v["link"], ts=v["ts"].isoformat(timespec="minutes"), src=v["src"], lang=v["lang"],
                        fw="fedwatch" in t or "페드워치" in t, q=sorted(v["q"]), probs=probs))
    out.sort(key=lambda x: x["ts"], reverse=True)
    return out


# ── 폭락 가능성 (FedWatch 주변 신호만으로, 5단계) ──
FOMC = ["2026-10-28", "2026-12-09", "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-16", "2027-07-28", "2027-09-22", "2027-10-27", "2027-12-08"]
GRADES = ["매우낮음", "낮음", "중간", "높음", "매우높음"]
CUTW = re.compile(r"\bcuts?\b|\bcutting\b|easing|lower rates|인하", re.I)
HOLDW = re.compile(r"\bholds?\b|\bholding\b|pause|unchanged|steady|동결", re.I)
HIKEW = re.compile(r"\bhikes?\b|\bhiking\b|raise|tighten|인상", re.I)
BIGW = re.compile(r"emergency|intermeeting|\b(50|75)\s?(bp|bps|basis)|half[- ]point|jumbo|긴급|빅컷|0\.5\s?%?p", re.I)
STRESSW = re.compile(r"recession|crash|sell-?off|plunge|plummet|panic|turmoil|crisis|meltdown|\brout\b|default|bank run|contagion|경기\s?침체|폭락|급락|위기|패닉|공포|발작", re.I)


def crash_rating(nw, figs, now, fw24, fw7):
    age = lambda x: now - datetime.fromisoformat(x["ts"])
    h24 = [x["title"] for x in nw if age(x) <= timedelta(hours=24)]
    h72 = [x["title"] for x in nw if age(x) <= timedelta(hours=72)]
    h7 = [x["title"] for x in nw]
    c = lambda rx, hs: sum(1 for t in hs if rx.search(t))
    words = dict(cut=c(CUTW, h24), hold=c(HOLDW, h24), hike=c(HIKEW, h24))
    # A. 인하를 서두르나 (가중치 2배): 긴급·빅컷 인하 기사 / 인하 쪽 기사가 동결+인상보다 많음 / 기사 속 인하 확률이 큼
    big = sum(1 for t in h72 if BIGW.search(t) and CUTW.search(t))
    emerg = sum(1 for t in h72 if re.search(r"emergency|intermeeting|긴급", t, re.I) and CUTW.search(t))
    cutf = sorted(f["v"] for f in figs if f["kind"] == "cut" and now - datetime.fromisoformat(f["ts"]) <= timedelta(hours=72))
    cutmed = cutf[len(cutf) // 2] if cutf else None
    A = 2 if (emerg >= 1 or big >= 3) else 1 if ((words["cut"] >= 5 and words["cut"] > words["hold"] + words["hike"]) or (cutmed is not None and cutmed >= 60) or big >= 1) else 0
    # B. 불안한 말 (침체·폭락·패닉…)이 평소보다 많은가
    s24 = c(STRESSW, h24) / len(h24) if len(h24) >= 10 else None
    s7 = c(STRESSW, h7) / len(h7) if h7 else 0
    B = 0 if s24 is None else 2 if (s24 >= 0.20 and s24 >= 2 * s7) else 1 if ((s24 >= 0.10 and s24 >= 1.5 * s7) or s24 >= 0.25) else 0
    # C. FedWatch 언급이 평소보다 몰리나 — FOMC 주간엔 원래 늘어나니 절반으로 깎아서 봄
    today = now.date()
    fomc_week = any(-1 <= (datetime.fromisoformat(x).date() - today).days <= 3 for x in FOMC)
    r = fw24 / (fw7 / 7) if fw7 else None
    radj = None if r is None else r / 2 if fomc_week else r
    C = 0 if radj is None else 2 if radj >= 3 else 1 if radj >= 2 else 0
    score = 2 * A + B + C
    g = 0 if score == 0 else 1 if score <= 2 else 2 if score <= 4 else 3 if score <= 6 else 4
    return dict(g=g, grade=GRADES[g], score=score, A=A, B=B, C=C, words=words, big=big, emerg=emerg, cutmed=cutmed,
                s24=None if s24 is None else round(s24, 3), s7=round(s7, 3), stress24=c(STRESSW, h24), n24=len(h24),
                r=None if r is None else round(r, 2), radj=None if radj is None else round(radj, 2), fomc_week=fomc_week,
                next_fomc=next((x for x in FOMC if datetime.fromisoformat(x).date() >= today), None))


def main():
    now = datetime.now(timezone.utc)
    try: old = json.load(open(OUT))
    except Exception: old = {}
    nw = news()
    if not nw and old.get("news"):
        nw = old["news"]; note("뉴스 전부 실패 — 이전 값 유지")
    age = lambda x: now - datetime.fromisoformat(x["ts"])
    byq = {q: dict(h24=sum(1 for x in nw if q in x.get("q", []) and age(x) <= timedelta(hours=24)), d7=sum(1 for x in nw if q in x.get("q", [])))
           for _, q in QUERIES}
    n24 = sum(1 for x in nw if age(x) <= timedelta(hours=24))
    fw24 = sum(1 for x in nw if age(x) <= timedelta(hours=24) and ("FedWatch" in x.get("q", []) or "페드워치" in x.get("q", []) or x.get("fw")))
    fw7 = sum(1 for x in nw if "FedWatch" in x.get("q", []) or "페드워치" in x.get("q", []) or x.get("fw"))
    figs = [dict(kind=p[0], v=p[1], mon=p[2] if len(p) > 2 else None, ts=x["ts"], title=x["title"], src=x["src"], link=x["link"])
            for x in nw for p in x["probs"]]
    def med(k):
        v = sorted(f["v"] for f in figs if f["kind"] == k and now - datetime.fromisoformat(f["ts"]) <= timedelta(hours=72))
        return None if not v else v[len(v) // 2]
    rt = crash_rating(nw, figs, now, fw24, fw7)
    snap = dict(t=now.isoformat(timespec="minutes"), n24=n24, fw24=fw24, q={q: v["h24"] for q, v in byq.items()},
                cut=med("cut"), hold=med("hold"), hike=med("hike"), g=rt["g"], sc=rt["score"])
    hist = [h for h in old.get("hist", []) if datetime.fromisoformat(h["t"]) >= now - timedelta(days=30)] + [snap]
    json.dump(dict(ts=int(now.timestamp()), rating=rt, news=nw[:60], figs=figs[:30], diag=DIAG,
                   counts=dict(n24=n24, fw24=fw24, n7d=len(nw), fw7d=fw7, byq=byq),
                   news_probs=dict(cut=med("cut"), hold=med("hold"), hike=med("hike"), n=sum(1 for f in figs if now - datetime.fromisoformat(f["ts"]) <= timedelta(hours=72))), hist=hist[-3000:]),
              open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
    print("FedWatch 주변 폭락 가능성:", rt["grade"], rt, "| 24시간 기사", n24, "· FedWatch 언급", fw24, "· 제목 속 수치", len(figs))


if __name__ == "__main__":
    main()
