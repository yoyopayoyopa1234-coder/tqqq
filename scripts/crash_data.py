"""대폭락 조짐 원자료 → crash_raw.json (FRED 경제·금융 지표, 12시간 캐시).

계산은 crash_risk.py 가 이 파일과 tq40.json(S&P500·나스닥100 종가)으로 한다.
각 시계열은 [[날짜, 값], ...] 그대로 저장(발표 시차는 계산 쪽에서 반영).
"""
import csv, io, json, os, sys, time
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(__file__))
from yahoo_data import get

OUT = os.path.join(os.path.dirname(__file__), "..", "crash_raw.json")
SERIES = {
    # 금리·신용
    "T10Y3M": "10년-3개월 국채 금리차 (일)",
    "T10Y2Y": "10년-2년 국채 금리차 (일)",
    "BAA10Y": "Baa 회사채 - 10년 국채 스프레드 (일)",
    "BAMLH0A0HYM2": "하이일드 OAS (일)",
    "NFCI": "시카고 연은 금융여건지수 (주)",
    "STLFSI4": "세인트루이스 연은 금융스트레스지수 (주)",
    "VIXCLS": "VIX (일)",
    "VXOCLS": "VXO (일, 1986~2021)",
    "DFF": "연방기금 실효금리 (일)",
    # 실물 경기
    "SAHMREALTIME": "샴 법칙 실시간 (월)",
    "UNRATE": "실업률 (월)",
    "ICSA": "신규 실업수당 청구 (주)",
    "PERMIT": "주택 건축허가 (월)",
    "DRTSCILM": "은행 기업대출 기준 강화 비율 (분기)",
    "TDSP": "가계 부채상환비율 (분기)",
    "DRSFRMACBS": "주택담보대출 연체율 (분기)",
    # 밸류에이션
    "NCBEILQ027S": "비금융기업 주식 시가총액 (분기)",
    "GDP": "명목 GDP (분기)",
}


def fred(sid):
    rows = []
    for row in csv.reader(io.StringIO(get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"))):
        try:
            rows.append([row[0], float(row[1])])
        except Exception:
            pass
    return rows


def main():
    now = time.time()
    old = None
    if os.path.exists(OUT):
        try:
            old = json.load(open(OUT))
        except Exception:
            old = None
    if old and now - old.get("ts", 0) < 12 * 3600 and all(k in old.get("series", {}) for k in SERIES):
        print("crash_raw 캐시 사용", datetime.fromtimestamp(old["ts"], timezone.utc).strftime("%m-%d %H:%M"))
        return
    series, fails = {}, []
    for sid in SERIES:
        try:
            rows = fred(sid)
            if len(rows) < 10:
                raise ValueError(f"{len(rows)}행")
            series[sid] = rows
            print(f"{sid}: {len(rows)}행 {rows[0][0]} ~ {rows[-1][0]}")
        except Exception as e:
            fails.append(sid)
            print(f"{sid} 실패: {e}")
            if old and sid in old.get("series", {}):
                series[sid] = old["series"][sid]
    if not series:
        print("전부 실패 — 기존 파일 유지")
        return
    json.dump({"ts": int(now), "names": SERIES, "fails": fails, "series": series}, open(OUT, "w"), separators=(",", ":"))
    print("저장", OUT, f"실패 {fails}")


if __name__ == "__main__":
    main()
