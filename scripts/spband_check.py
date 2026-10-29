"""S&P 반반형 진입탈출선(S&P500 200일선 ±2.5%) 2차 검증 → spband_check.json (15분마다)

spband.html 의 자바스크립트와 별개로 tq40.json(40년 S&P500 종가)에서 200일선·밴드 상태·마지막 신호일을 다시 계산하고,
TQQQ 신호판(tq.json, 같은 SPX ±2.5% 규칙)의 값과도 대조한다. 페이지는 이 파일과 자기 계산을 비교해 일치/불일치를 보여준다.
"""
import json, time
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
BAND = 0.025


def main():
    J = json.load(open("tq40.json")); T = json.load(open("tq.json"))["spx"]
    d, sp = J["d"], J["spx"]; n = len(d)
    ma = [None] * n; s = 0.0
    for i, v in enumerate(sp):
        s += v
        if i >= 200: s -= sp[i - 200]
        if i >= 199: ma[i] = s / 200
    on = False; st = []; sig = []
    for i in range(n):
        if ma[i] is not None:
            if not on and sp[i] > ma[i] * (1 + BAND): on = True; sig.append((d[i], "IN", sp[i]))
            elif on and sp[i] < ma[i] * (1 - BAND): on = False; sig.append((d[i], "OUT", sp[i]))
        st.append(on)
    i = n - 1; m = ma[i]
    me = dict(date=d[i], idx=round(sp[i], 2), ma200=round(m, 2), up=round(m * (1 + BAND), 2), lo=round(m * (1 - BAND), 2),
              state="IN" if st[i] else "OUT", since=sig[-1][0] if sig else None, n_signals=len(sig))
    checks = []
    def chk(name, ok, detail): checks.append(dict(name=name, ok=bool(ok), detail=detail))
    chk("날짜 (40년 파일 ↔ 신호판)", d[i] == T["date"], f"{d[i]} / {T['date']}")
    chk("S&P500 종가", abs(sp[i] / T["idx"] - 1) < 0.0005, f"{sp[i]:,.2f} / {T['idx']:,.2f}")
    chk("200일선", abs(m / T["ma200"] - 1) < 0.0005, f"{m:,.2f} / {T['ma200']:,.2f}")
    chk("진입선 (+2.5%)", abs(me["up"] / T["up"] - 1) < 0.0005, f"{me['up']:,.2f} / {T['up']:,.2f}")
    chk("탈출선 (−2.5%)", abs(me["lo"] / T["lo"] - 1) < 0.0005, f"{me['lo']:,.2f} / {T['lo']:,.2f}")
    chk("투자 중 / 쉬는 중", me["state"] == T["state"], f"{me['state']} / {T['state']}")
    ent = (T.get("cycle") or {}).get("entry_date") if T["state"] == "IN" else None
    if ent: chk("신호 시작일", me["since"] == ent, f"{me['since']} / {ent}")
    final = J.get("bar_final")
    notes = []
    if final is False: notes.append("지금 값은 장중 실시간가 기준입니다. 미국 장 마감(한국 아침 5~6시) 뒤 15분 안에 종가로 확정됩니다.")
    gap = (sp[i] / me["lo"] - 1) * 100 if st[i] else (me["up"] / sp[i] - 1) * 100
    if abs(gap) < 1.0: notes.append(f"{'탈출선' if st[i] else '진입선'}까지 {abs(gap):.2f}% — 오늘 종가에 신호가 바뀔 수 있는 거리입니다.")
    out = dict(ts=int(time.time()), at_kst=datetime.now(KST).strftime("%m-%d %H:%M"), bar_final=final, mine=me,
               board=dict(date=T["date"], idx=T["idx"], ma200=T["ma200"], up=T["up"], lo=T["lo"], state=T["state"], since=ent),
               checks=checks, ok=all(c["ok"] for c in checks), notes=notes, recent=[dict(date=a, kind=b, idx=round(c, 2)) for a, b, c in sig[-12:]])
    json.dump(out, open("spband_check.json", "w"), ensure_ascii=False, separators=(",", ":"))
    print("spband_check", "OK" if out["ok"] else "MISMATCH", me)


if __name__ == "__main__":
    main()
