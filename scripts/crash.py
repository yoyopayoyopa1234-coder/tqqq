"""코로나급 폭락 가능성 지수 → crash.json (15분마다)

기준은 두 가지 숫자뿐:
  ① 뉴스 숫자 — 최근 24시간 시장 뉴스 제목 중 '폭락·급락·패닉·붕괴' 같은 단어가 들어간 제목의 수와 비율
  ② 의견 숫자 — 전망·경고·의견이 담긴 제목 중 '폭락 경고(비관)' 대 '반등·저가매수(낙관)' 수
Google 뉴스 RSS(영어·한국어) + Bing 뉴스 RSS 제목을 모아 중복을 지우고 센다. 통계적 확률이 아니라 뉴스 분위기를 0~100으로 옮긴 지수다.
"""
import json, os, re, sys, time
import html as H
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote
sys.path.insert(0, os.path.dirname(__file__))
from yahoo_data import get

OUT = os.path.join(os.path.dirname(__file__), "..", "crash.json")
KST = timezone(timedelta(hours=9))
Q = [("en", "stock market"), ("en", "Wall Street stocks"), ("en", "Nasdaq"), ("en", "S&P 500"), ("en", "stock market crash"), ("en", "stock market outlook"),
     ("ko", "증시"), ("ko", "뉴욕증시"), ("ko", "나스닥"), ("ko", "증시 폭락"), ("ko", "증시 전망")]
MARKET = re.compile(r"stock|wall street|nasdaq|s&p|dow|market|equit|shares|investor|증시|주식|나스닥|다우|코스피|코스닥|뉴욕|월가|시장|투자", re.I)
CRASH = re.compile(r"crash|plunge|plummet|meltdown|collapse|rout|bloodbath|panic|free ?fall|sell-?off|tumble|wipe ?out|black monday|circuit breaker|bear market|worst (day|week|month)|"
                   r"폭락|급락|패닉|붕괴|투매|서킷브레이커|블랙먼데이|검은 ?(월|화|수|목|금)요일|약세장|쇼크|추락", re.I)
OPIN = re.compile(r"warn|predict|forecast|expect|outlook|says|analyst|strategist|could|may |might|will |risk of|call|target|bet|see[s]? |"
                  r"전망|경고|예상|우려|분석|진단|가능성|관측|의견|목표|조언|\"|“|…", re.I)
BEAR = re.compile(r"crash|plunge|collapse|meltdown|bubble|recession|bear|worse|more pain|downside|further (fall|drop|decline|losses)|correction|sell|danger|risk|warn|"
                  r"폭락|급락|붕괴|버블|거품|침체|약세|하락|추가 ?하락|조정|경고|위험|우려|매도|더 ?떨어", re.I)
BULL = re.compile(r"rebound|rally|recover|bottom|buy the dip|buying opportunity|oversold|bull|upside|bounce|overdone|cheap|bargain|undervalued|"
                  r"반등|회복|바닥|저가 ?매수|매수 ?기회|과매도|강세|상승|낙관|과도한 ?공포|저평가|줍줍", re.I)
DIAG = []


def note(*a):
    m = " ".join(str(x) for x in a); print(m); DIAG.append(m[:300])


def collect(now):
    items = {}
    def add(title, src, link, ts, lang):
        t = re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", title or ""))).strip()
        t = re.sub(r"\s[-|–]\s[^-|–]{2,40}$", "", t)          # 끝의 ' - 매체명' 제거
        k = re.sub(r"[^0-9a-z가-힣]", "", t.lower())[:60]
        if len(k) < 8 or k in items or not MARKET.search(t): return
        items[k] = dict(t=t, src=src, link=link, ts=ts, lang=lang)
    for lang, q in Q:
        for when in ("1d", "7d"):
            url = (f"https://news.google.com/rss/search?q={quote(q)}+when:{when}&hl=en-US&gl=US&ceid=US:en" if lang == "en"
                   else f"https://news.google.com/rss/search?q={quote(q)}+when:{when}&hl=ko&gl=KR&ceid=KR:ko")
            try: root = ET.fromstring(get(url))
            except Exception as e: note("구글뉴스 실패", q, when, type(e).__name__, str(e)[:80]); continue
            n = 0
            for it in root.iter("item"):
                try: ts = parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc)
                except Exception: continue
                s = it.find("source"); add(it.findtext("title"), (s.text if s is not None else "") or "Google 뉴스", it.findtext("link") or "", ts, lang); n += 1
            note("구글뉴스", q, when, n)
        try:
            root = ET.fromstring(get(f"https://www.bing.com/news/search?q={quote(q)}&format=rss&qft=sortbydate%3d%221%22")); n = 0
            for it in root.iter("item"):
                try: ts = parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc)
                except Exception: continue
                src = next((ch.text for ch in it if ch.tag.endswith("Source") and ch.text), "Bing 뉴스"); add(it.findtext("title"), src, it.findtext("link") or "", ts, lang); n += 1
            note("빙뉴스", q, n)
        except Exception as e: note("빙뉴스 실패", q, type(e).__name__, str(e)[:80])
    return list(items.values())


def stats(items, now, hours):
    w = [x for x in items if timedelta(0) <= now - x["ts"] <= timedelta(hours=hours)]
    crash = [x for x in w if CRASH.search(x["t"])]
    op = [x for x in w if OPIN.search(x["t"])]
    bear, bull = [], []
    for x in op:
        b, u = len(BEAR.findall(x["t"])), len(BULL.findall(x["t"]))
        if b > u: bear.append(x)
        elif u > b: bull.append(x)
    return dict(n=len(w), crash=len(crash), op=len(op), bear=len(bear), bull=len(bull)), crash, bear, bull


def score(s):
    """뉴스 점수: 폭락 제목 비율 5%→0 · 45%→100 / 의견 점수: 비관 비율 40%→0 · 85%→100 (의견 10건 미만이면 뉴스 점수만)"""
    cs = s["crash"] / s["n"] if s["n"] else 0
    a = max(0.0, min(100.0, (cs - 0.05) / 0.40 * 100))
    tot = s["bear"] + s["bull"]; bs = s["bear"] / tot if tot else None
    b = None if tot < 10 else max(0.0, min(100.0, (bs - 0.40) / 0.45 * 100))
    return dict(news=round(a, 1), opin=None if b is None else round(b, 1), total=round(a if b is None else (a + b) / 2, 1),
                crash_share=round(cs * 100, 1), bear_share=None if bs is None else round(bs * 100, 1))


def main():
    now = datetime.now(timezone.utc)
    try: old = json.load(open(OUT))
    except Exception: old = {}
    items = collect(now)
    if len(items) < 30:
        note("뉴스 수집 부족", len(items), "— 이전 값 유지")
        if old: old["diag"] = DIAG; json.dump(old, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
        return
    s24, c24, be24, bu24 = stats(items, now, 24); s7, *_ = stats(items, now, 24 * 7)
    sc24, sc7 = score(s24), score(s7)
    ser = lambda x: dict(t=x["t"][:140], src=x["src"][:30], link=x["link"], ts=x["ts"].isoformat(timespec="minutes"), lang=x["lang"])
    top = lambda a: [ser(x) for x in sorted(a, key=lambda x: x["ts"], reverse=True)[:15]]
    hist = old.get("hist", [])
    if not hist or now.timestamp() - hist[-1][0] >= 3300:      # 1시간에 한 번 기록
        hist.append([int(now.timestamp()), sc24["total"], s24["n"], s24["crash"], s24["bear"], s24["bull"]])
    out = dict(ts=int(now.timestamp()), at_kst=now.astimezone(KST).strftime("%m-%d %H:%M"), d24=s24, d7=s7, s24=sc24, s7=sc7,
               crash=top(c24), bear=top(be24), bull=top(bu24), hist=hist[-24 * 120:], diag=DIAG)
    json.dump(out, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
    note("crash", sc24, s24)


if __name__ == "__main__":
    main()
