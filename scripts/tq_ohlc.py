"""TQQQ 일·주·월봉 시세 → tqqq_data.json (분석 페이지용, Global M2는 dashboard/data.json 공유)."""
import json, os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(__file__))
from yahoo_data import yahoo

def main():
    out = {"updated": datetime.now(timezone.utc).isoformat(timespec="minutes"), "ohlc": {}}
    for key, iv in (("TQQQ_1d", "1d"), ("TQQQ_1wk", "1wk"), ("TQQQ_1mo", "1mo")):
        try:
            out["ohlc"][key] = yahoo("TQQQ", iv); print(key, len(out["ohlc"][key]))
        except Exception as e:
            print("FAIL", key, e)
    try:
        out["ohlc"]["QQQ_1d"] = yahoo("QQQ", "1d"); print("QQQ_1d", len(out["ohlc"]["QQQ_1d"]))   # 3/161/185 매매법
    except Exception as e:
        print("FAIL QQQ_1d", e)
    try:
        out["ohlc"]["QQQ_1mo"] = yahoo("QQQ", "1mo"); print("QQQ_1mo", len(out["ohlc"]["QQQ_1mo"]))   # RSI는 QQQ 기준
    except Exception as e:
        print("FAIL QQQ_1mo", e)
    if not all(k in out["ohlc"] for k in ("TQQQ_1d", "TQQQ_1wk", "TQQQ_1mo")):
        raise SystemExit("일부 시세를 받지 못함 — 기존 tqqq_data.json 유지")
    json.dump(out, open("tqqq_data.json", "w"), separators=(",", ":"))

if __name__ == "__main__":
    main()
