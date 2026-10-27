"""FedWatch 페이지 자료 → fedwatch.json (매 실행 · 15분마다).

CME FedWatch 사이트(확률 화면)는 막혀 있어서, 그 숫자를 인용한 글을 여기저기서 긁어 모은다.
  · 뉴스: Google 뉴스 RSS(제목) · Bing 뉴스 RSS(제목+요약) · 네이버/다음 뉴스 검색(미리보기 문장)
  · 검색: DuckDuckGo(최근 1일) · Google 검색(되면)
  · 커뮤니티: 디시인사이드 통합검색(제목+본문 미리보기)
각 글에서 'FedWatch·페드워치·확률·odds' 근처의 퍼센트를 인상/동결/인하로 나누고, 어느 회의(달) 얘기인지 붙인다.
회의마다 최근 인용 숫자의 가운데값 = 'FedWatch 기준 인상 확률(인용값)'.
그 밖에 언급 수(검색어별 24시간/7일), 반응 뉴스, 커뮤니티 글도 저장. 기록은 30일 쌓아 추이를 그린다.
"""
import json, os, re, sys, gzip
import html as H
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote
sys.path.insert(0, os.path.dirname(__file__))
from yahoo_data import get

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "fedwatch.json")
KST = timezone(timedelta(hours=9))
# FOMC 결정일(미국 날짜, 발표 = 한국 다음 날 새벽 3~4시). 2027년은 연준 일정 기준 — 바뀌면 여기만 고치면 됨
FOMC = ["2026-10-28", "2026-12-09", "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-16", "2027-07-28", "2027-09-22", "2027-10-27", "2027-12-08"]
DIAG = []


def note(*a):
    m = " ".join(str(x) for x in a); print(m); DIAG.append(m[:400])


# ── 숫자 뽑기 ──
MON = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
MRE = re.compile(r"\b(january|february|march|april|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)\b|(\d{1,2})월")
REL_THIS = re.compile(r"이달|이번 ?달|this month|이번 ?(회의|fomc)|this week|이번 ?주|next week|다음 ?주|tomorrow|내일|오늘|today|wednesday|수요일|this meeting|upcoming meeting|next meeting|다음 ?회의|이번 ?금리 ?결정")
REL_NEXT = re.compile(r"다음 ?달|next month")
PCT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s?%")
KW = {"cut": ["cut", "cuts", "easing", "lower rates", "reduction", "인하"], "hold": ["hold", "pause", "unchanged", "steady", "동결", "유지"], "hike": ["hike", "raise", "increase", "tighten", "인상"]}
EXW = ["cpi", "pce", "gdp", "물가", "실업", "yield", "수익률", "inflation", "인플레", "성장률", "지지율", "상승률", "하락률", "점유율", "증가율", "주가", "올랐", "내렸", "상승", "하락"]
CUE = ("fedwatch", "fed watch", "페드워치", "페드와치", "odds", "probability", "chance", "확률", "가능성", "price in", "priced", "bets", "futures", "traders", "선물", "kalshi", "polymarket")


def next_fomc(d):
    """그 날짜(미국) 기준 아직 결정 전인 첫 FOMC"""
    return next((x for x in FOMC if x >= d.isoformat()), None)


def kind_after(t, pos):
    best = None
    for k, ws in KW.items():
        for w in ws:
            j = t.find(w, pos)
            if 0 <= j - pos <= 20 and (best is None or j < best[0]): best = (j, k)
    return best[1] if best else None


def month_of(t, pos, ts, kind=None, end=None):
    """숫자 앞 40자 안의 가장 가까운 달 이름 → (달, 확실?). 없으면 '이달·다음 주·내일' 같은 말 → 그때의 다음 회의. 그것도 없으면 None"""
    best = None
    for m in MRE.finditer(t):
        if m.start() >= pos: break
        mo = MON[m.group(1)[:3]] if m.group(1) else int(m.group(2))
        if 1 <= mo <= 12 and pos - m.start() <= 40: best = mo
    if best: return best, True
    # 숫자 뒤 'chance of a December hike' — 그 달 바로 뒤 말이 숫자의 종류와 같을 때만
    if end is not None:
        stop = end + 35
        for ch in ".,/;·|\n(":
            j = t.find(ch, end)
            if 0 <= j < stop: stop = j
        for m in MRE.finditer(t, end, min(len(t), stop)):
            mo = MON[m.group(1)[:3]] if m.group(1) else int(m.group(2))
            if 1 <= mo <= 12 and kind_after(t, m.end()) == kind: return mo, True
    win = t[max(0, pos - 60): pos + 40]
    us = (ts - timedelta(hours=5)).date()
    if REL_NEXT.search(win):
        return (us.month % 12) + 1, True
    if REL_THIS.search(win):
        nf = next_fomc(us); return (int(nf[5:7]) if nf else None), True
    return None, False


def classify(raw, ts):
    """'동결 약 86% / 25bp 인상 약 14%' · 'Price 90% Odds of a Hold' → [[종류, 값, 달, 달 확실?]]. %p(포인트)·CPI 같은 숫자는 뺌"""
    t = raw.lower(); out = []
    if not any(c in t for c in CUE): return out
    for m in PCT.finditer(raw):
        if raw[m.end():m.end() + 1] in ("p", "P"): continue
        val = float(m.group(1))
        if val > 100: continue
        cands = []
        for k, ws in list(KW.items()) + [("ex", EXW)]:
            for w in ws:
                for mm in re.finditer(re.escape(w), t):
                    if mm.end() <= m.start(): dist = m.start() - mm.end(); side = "b"
                    elif mm.start() >= m.end(): dist = mm.start() - m.end(); side = "a"
                    else: continue
                    if dist <= 25: cands.append((dist, side, k))
        if not cands: continue
        before = sorted(c for c in cands if c[1] == "b")
        pick = before[0] if before and before[0][0] <= 12 else min(cands)
        if pick[2] == "ex": continue
        # 숫자 주변 80자 안에 확률 쪽 말이 있어야 (기사 속 다른 퍼센트 배제)
        if not any(c in t[max(0, m.start() - 80): m.end() + 80] for c in CUE): continue
        mo, sure = month_of(t, m.start(), ts, pick[2], m.end())
        out.append([pick[2], val, mo, sure])
    return out


# ── 가져오기 ──
BH = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"}


def fetch(url, ref=None):
    h = dict(BH)
    if ref: h["Referer"] = ref
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=20) as r:
        b = r.read()
        if r.headers.get("Content-Encoding") == "gzip": b = gzip.decompress(b)
        return b.decode("utf-8", "replace")


def strip(x):
    x = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", x, flags=re.S | re.I)
    x = re.sub(r"<(br|/p|/li|/div|/h\d|/tr)[^>]*>", "\n", x, flags=re.I)
    return re.sub(r"[ \t\r\f\v]+", " ", H.unescape(re.sub(r"<[^>]+>", " ", x))).strip()


ITEMS = []   # 모든 출처의 글: dict(src, kind(news/search/comm), title, text, link, ts, probs, q)


def add(src, kind, title, text, link, ts, q=None):
    ITEMS.append(dict(src=src, kind=kind, title=title.strip(), text=(text or "").strip()[:400], link=link, ts=ts, q=q,
                      probs=classify(title + " \n " + (text or ""), ts)))


GN = [("en", "FedWatch"), ("en", "FedWatch rate hike probability"), ("en", "\"rate cut\" odds Fed"), ("en", "fed funds futures"),
      ("ko", "페드워치"), ("ko", "금리 인상 확률 연준"), ("ko", "금리 인하 확률 연준")]


def google_news():
    for lang, q in GN:
        url = (f"https://news.google.com/rss/search?q={quote(q)}+when:7d&hl=en-US&gl=US&ceid=US:en" if lang == "en"
               else f"https://news.google.com/rss/search?q={quote(q)}+when:7d&hl=ko&gl=KR&ceid=KR:ko")
        try: root = ET.fromstring(get(url))
        except Exception as e: note("구글뉴스 실패", q, type(e).__name__, str(e)[:80]); continue
        n = 0
        for it in root.iter("item"):
            try: ts = parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc)
            except Exception: continue
            s = it.find("source")
            add((s.text if s is not None else "") or "Google 뉴스", "news", it.findtext("title") or "", "", it.findtext("link") or "", ts, q); n += 1
        note("구글뉴스", q, n)


def bing_news():
    for q in ("FedWatch", "CME FedWatch probability", "Fed rate hike odds", "페드워치"):
        url = f"https://www.bing.com/news/search?q={quote(q)}&format=rss&qft=sortbydate%3d%221%22"
        try: root = ET.fromstring(fetch(url))
        except Exception as e: note("빙뉴스 실패", q, type(e).__name__, str(e)[:80]); continue
        n = 0
        for it in root.iter("item"):
            try: ts = parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc)
            except Exception: ts = datetime.now(timezone.utc)
            src = ""
            for ch in it:
                if ch.tag.endswith("Source"): src = ch.text or ""
            add(src or "Bing 뉴스", "news", strip(it.findtext("title") or ""), strip(it.findtext("description") or ""), it.findtext("link") or "", ts, q); n += 1
        note("빙뉴스", q, n)


RELT = re.compile(r"(\d+)\s?(분|시간|일)\s?전|(\d+)\s?(minutes?|mins?|hours?|days?)\s?ago")


def rel_ts(s, now):
    m = RELT.search(s)
    if not m: return None
    n = int(m.group(1) or m.group(3)); u = m.group(2) or m.group(4)
    return now - (timedelta(minutes=n) if u.startswith(("분", "min")) else timedelta(hours=n) if u.startswith(("시간", "hour")) else timedelta(days=n))


def windows(src, kind, page, url, now, cue, default_age):
    """검색 결과 페이지에서 단서 단어 둘레 문장을 잘라 숫자 뽑기 (구조가 자주 바뀌는 사이트용)"""
    text = strip(page); n = 0; seen = set()
    for m in re.finditer(cue, text, re.I):
        w = text[max(0, m.start() - 220): m.end() + 260].replace("\n", " ")
        key = re.sub(r"\W", "", w[150:330])
        if key in seen: continue
        seen.add(key)
        ts = rel_ts(text[max(0, m.start() - 400): m.end() + 400], now) or (now - default_age)
        add(src, kind, "", w, url, ts); n += 1
    return n


def kr_search(now):
    for nm, url in (("네이버 뉴스", "https://search.naver.com/search.naver?where=news&query={q}&sort=1&pd=4"),
                    ("다음 뉴스", "https://search.daum.net/search?w=news&q={q}&sort=recency&period=d")):
        for q in ("페드워치", "페드워치 인상 확률"):
            u = url.format(q=quote(q))
            try: page = fetch(u)
            except Exception as e: note(nm, "실패", q, type(e).__name__, str(e)[:80]); continue
            n = windows(nm, "search", page, u, now, r"페드워치|fedwatch", timedelta(hours=12))
            note(nm, q, "길이", len(page), "문장", n)


def web_search(now):
    for nm, url in (("DuckDuckGo", "https://html.duckduckgo.com/html/?q={q}&df=d"),
                    ("Google 검색", "https://www.google.com/search?q={q}&tbs=qdr:d&hl=ko&num=20")):
        for q in ("CME FedWatch rate hike probability", "페드워치 금리 인상 확률"):
            u = url.format(q=quote(q))
            try: page = fetch(u, "https://duckduckgo.com/" if "duck" in u else "https://www.google.com/")
            except Exception as e: note(nm, "실패", q, type(e).__name__, str(e)[:80]); continue
            n = windows(nm, "search", page, u, now, r"fedwatch|fed watch|페드워치", timedelta(hours=12))
            note(nm, q, "길이", len(page), "문장", n, "| 앞:", re.sub(r"\s+", " ", strip(page)[:120]))


def dcinside(now):
    for kw in ("fedwatch", "페드워치", "페드와치"):
        enc = quote(kw).replace("%", ".")
        url = f"https://search.dcinside.com/post/p/1/sort/latest/q/{enc}"
        try: t = fetch(url, "https://search.dcinside.com/")
        except Exception as e: note("디시 실패", kw, type(e).__name__, str(e)[:80]); continue
        n = 0
        for it in re.findall(r"<li>(.*?)</li>", t, re.S):
            a = re.search(r'<a href="([^"]+)"[^>]*class="tit_txt"[^>]*>(.*?)</a>', it, re.S)
            d = re.search(r'<span class="date_time">\s*([0-9.: ]+)</span>', it)
            g = re.search(r'<a [^>]*class="sub_txt"[^>]*>(.*?)</a>', it, re.S)
            sn = re.search(r'<p class="link_dsc_txt[^"]*"[^>]*>(.*?)</p>', it, re.S)
            if not a or not d: continue
            try: ts = datetime.strptime(d.group(1).strip()[:16], "%Y.%m.%d %H:%M").replace(tzinfo=KST).astimezone(timezone.utc)
            except Exception: continue
            add("디시 " + (strip(g.group(1)) if g else ""), "comm", strip(a.group(2)), strip(sn.group(1)) if sn else "", a.group(1).replace("&amp;", "&"), ts, kw); n += 1
        note("디시", kw, n)


# ── 회의별 인상 확률(인용값) ──
def estimate(items, now):
    us_today = (now - timedelta(hours=5)).date()
    meets = [x for x in FOMC if x >= us_today.isoformat()][:3]
    figs = []
    for it in items:
        for k, v, mo, sure in it["probs"]:
            usd = (it["ts"] - timedelta(hours=5)).date()
            if mo is None:   # 달이 안 적힌 숫자는 그때의 다음 회의 얘기로 봄(대부분의 헤드라인)
                nf = next_fomc(usd); mo = int(nf[5:7]) if nf else None
            mt = next((x for x in FOMC if int(x[5:7]) == mo and x >= usd.isoformat()), None)
            if mt is None or mt not in meets: continue
            figs.append(dict(meet=mt, kind=k, v=v, sure=sure, ts=it["ts"], src=it["src"], title=it["title"] or it["text"][:120],
                             text=it["text"], link=it["link"], skind=it["kind"]))
    res = []
    for mt in meets:
        F = [f for f in figs if f["meet"] == mt]
        row = dict(date=mt, n=len(F), window=None)
        G = []
        for win in (24, 72, 24 * 7):
            G = [f for f in F if now - f["ts"] <= timedelta(hours=win)]
            if G: row["window"] = win; break
        for k in ("hike", "hold", "cut"):
            v = sorted(f["v"] for f in G if f["kind"] == k)
            row[k] = (v[len(v) // 2] if len(v) % 2 else round((v[len(v) // 2 - 1] + v[len(v) // 2]) / 2, 1)) if v else None; row[k + "_n"] = len(v)
        # 인상 숫자가 없으면 '100 − 동결 − 인하'로 (인하 숫자가 없으면 0으로 봄) — 표시할 때 ≈ 표시
        row["hike_est"] = row["hike"]; row["derived"] = False
        if row["hike"] is None and row["hold"] is not None:
            row["hike_est"] = round(max(0.0, 100 - row["hold"] - (row["cut"] or 0)), 1); row["derived"] = True
        row["latest"] = max((f["ts"] for f in G), default=None)
        res.append(row)
    return res, figs


def main():
    now = datetime.now(timezone.utc)
    try: old = json.load(open(OUT))
    except Exception: old = {}
    for fn in (google_news, bing_news, lambda: kr_search(now), lambda: web_search(now), lambda: dcinside(now)):
        try: fn()
        except Exception as e: note("출처 실패", type(e).__name__, str(e)[:120])
    # 같은 글 합치기 (제목 앞부분, 없으면 문장)
    seen = {}
    for it in ITEMS:
        key = re.sub(r"\s+-\s+[^-]+$", "", it["title"]).lower()[:80] or re.sub(r"\W", "", it["text"])[:80]
        if key in seen:
            if it["q"]: seen[key]["qs"].add(it["q"])
            if len(it["probs"]) > len(seen[key]["probs"]): seen[key]["probs"] = it["probs"]; seen[key]["text"] = it["text"]
            continue
        it["qs"] = {it["q"]} if it["q"] else set(); seen[key] = it
    items = [x for x in seen.values() if now - x["ts"] <= timedelta(days=8)]
    items.sort(key=lambda x: x["ts"], reverse=True)
    meets, figs = estimate(items, now)
    if not items and old.get("meets"):
        note("모든 출처 실패 — 이전 값 유지"); meets = old["meets"]
    age = lambda x: now - x["ts"]
    news = [x for x in items if x["kind"] == "news" and x["title"]]
    comm = [x for x in items if x["kind"] == "comm"]
    fwq = lambda x: any(q and re.search(r"fedwatch|페드워치|페드와치", q, re.I) for q in x["qs"]) or bool(re.search(r"fedwatch|fed watch|페드워치|페드와치", x["title"] + x["text"], re.I))
    cnt = dict(n24=sum(1 for x in news if age(x) <= timedelta(hours=24)), n7d=len(news),
               fw24=sum(1 for x in news if age(x) <= timedelta(hours=24) and fwq(x)), fw7d=sum(1 for x in news if fwq(x)),
               c24=sum(1 for x in comm if age(x) <= timedelta(hours=24)), c7d=len(comm),
               byq={q: dict(h24=sum(1 for x in news if q in x["qs"] and age(x) <= timedelta(hours=24)), d7=sum(1 for x in news if q in x["qs"])) for _, q in GN})
    bysrc = {}
    for f in figs:
        if now - f["ts"] <= timedelta(hours=72): bysrc[f["skind"]] = bysrc.get(f["skind"], 0) + 1
    ser = lambda x: {**{k: v for k, v in x.items() if k not in ("ts", "qs", "q")}, "ts": x["ts"].isoformat(timespec="minutes")}
    iso = lambda v: v.isoformat(timespec="minutes") if isinstance(v, datetime) else v
    snap = dict(t=now.isoformat(timespec="minutes"), n24=cnt["n24"], fw24=cnt["fw24"], c24=cnt["c24"],
                m=[[m["date"], m["hike_est"], m["hold"], m["cut"]] for m in meets])
    hist = [h for h in old.get("hist", []) if "m" in h and datetime.fromisoformat(h["t"]) >= now - timedelta(days=30)] + [snap]
    out = dict(ts=int(now.timestamp()), meets=[{k: iso(v) for k, v in m.items()} for m in meets],
               figs=[{k: iso(v) for k, v in f.items()} for f in sorted(figs, key=lambda f: f["ts"], reverse=True)[:60]],
               counts=cnt, fig_src=bysrc, news=[ser(x) for x in news[:50]], comm=[ser(x) for x in comm[:30]], diag=DIAG, hist=hist[-3000:])
    json.dump(out, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
    for m in meets:
        print("FedWatch 인용", m["date"], "인상", m["hike_est"], ("(≈100−동결)" if m["derived"] else ""), "동결", m["hold"], "인하", m["cut"], "| 숫자", m["n"], "개")
    print("뉴스 24시간", cnt["n24"], "· FedWatch 언급", cnt["fw24"], "· 커뮤니티", cnt["c24"], "· 출처별 숫자", bysrc)


if __name__ == "__main__":
    main()
