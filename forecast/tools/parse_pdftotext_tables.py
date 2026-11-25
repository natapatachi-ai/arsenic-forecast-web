# ใช้ครั้งเดียวเพื่อถอดตารางโลหะในตะกอนจากข้อความ pdftotext -layout ของรายงานตะกอนรอบ 12-13
# รัน: pdftotext -layout report.pdf out.txt && python tools/parse_pdftotext_tables.py out.txt 13 out.csv
# งานปกติใช้ scripts/pcd_pdf_tables.py แทน
import re, sys, json
import pandas as pd
txt = open(sys.argv[1], encoding='utf-8').read().splitlines()
VAL = re.compile(r'^(<?\d+(\.\d+)?|-|ND)$')
STA = re.compile(r'\b([A-Z]{2}\d{2})\b')
out=[]; param=None; nexp=int(sys.argv[2])
for ln in txt:
    m = re.search(r'พารามิเตอร์โลหะหนักอื่นๆ \((.+?)\)', ln)
    if m: param=m.group(1); continue
    if param is None: continue
    if 'ภาคผนวก ค' in ln: break
    s = STA.search(ln)
    if not s: continue
    toks = ln.split()
    vals=[]
    for t in reversed(toks):
        if VAL.match(t): vals.append(t)
        else: break
    vals=vals[::-1]
    if len(vals) < nexp:
        print('SHORT', param, s.group(1), len(vals), ln.strip()[:120], file=sys.stderr); continue
    vals=vals[-nexp:]
    for i,v in enumerate(vals,1):
        out.append(dict(parameter=param, station_id=s.group(1), round=i, value_reported=v))
df=pd.DataFrame(out)
df.to_csv(sys.argv[3], index=False)
print(df.groupby('parameter').station_id.nunique())
