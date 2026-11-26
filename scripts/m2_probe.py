import json, re, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from yahoo_data import get
U = {"boj_data": "https://www.stat-search.boj.or.jp/api/v1/getDataCode?format=json&lang=en&db=MD02&code=MAM1NAM2M2MO&startDate=202501",
     "boj_meta": "https://www.stat-search.boj.or.jp/api/v1/getMetadata?format=json&lang=en&db=MD02",
     "cn_em": "https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_ECONOMY_CURRENCY_SUPPLY&columns=REPORT_DATE,BASIC_CURRENCY,CURRENCY,FREE_CASH&pageSize=5&sortColumns=REPORT_DATE&sortTypes=-1",
     "boe": "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom=01/Jan/2025&Dateto=now&SeriesCodes=LPMAUYN,LPMVWYW&CSVF=TN&UsingCodes=Y",
     "dbn_jp": "https://api.db.nomics.world/v22/series/BOJ/MD02/MAM1NAM2M2MO?observations=1",
     "dbn_cn": "https://api.db.nomics.world/v22/series?q=China%20M2%20money%20supply&limit=8"}
out = {}
for k, u in U.items():
    try:
        t = get(u); out[k] = t[:900]
        if k == "boj_meta":
            out[k + "_m2"] = [m.group(0)[:260] for m in re.finditer(r'\{[^{}]*M2[^{}]*\}', t)][:25]
        if k == "dbn_jp": out[k] = t[:300] + " ... " + t[-500:]
    except Exception as e: out[k] = f"FAIL {type(e).__name__} {str(e)[:150]}"
json.dump(out, open("m2_probe.json", "w"), ensure_ascii=False, indent=1)
