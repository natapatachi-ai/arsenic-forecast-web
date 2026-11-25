"""05b_watch_networks.py  ตัวเฝ้ารายงานของเครือข่ายอื่น (ทำงานต่อจาก 05_watch_pcd.py ในระบบอัปเดตอัตโนมัติ)

เครือข่ายที่เฝ้า
  salween   : สคพ.1 เชียงใหม่ "รายงานคุณภาพน้ำในแม่น้ำสาละวิน และลำน้ำสาขา ครั้งที่ N"
              https://epo01.pcd.go.th/th/information/more/358  (ตารางภาคผนวก ข เป็นตารางสะสมทุกครั้ง)
  mekong_ne : สคพ.9 อุดรธานี "รายงานผลคุณภาพน้ำแหล่งน้ำผิวดิน 30 สถานี ... ปีงบประมาณ พ.ศ.25xx ครั้งที่ k"
              https://epo09.pcd.go.th/th/information/more/579  (ใช้เฉพาะจุดแม่น้ำโขง NK05-NK08)

ขั้นตอน: หา "ครั้งที่" ใหม่ -> ดาวน์โหลด PDF -> ถอดแถวตามรหัสสถานี -> QC -> เขียนไฟล์ใน data/raw_tables/networks/
QC (ไม่ผ่าน = ไม่เขียนทับ, exit code 2)
  - สาละวิน: ค่าครั้งเก่าในตารางสะสมฉบับใหม่ต้องตรงกับข้อมูลเดิม >= 98% และครั้งใหม่ต้องมีค่า >= 3 จุด
  - โขงอีสาน: ต้องพบสารหนูครบ >= 3 จุด จาก 4 จุด และค่าที่อ่านได้ต้องเป็นตัวเลข/รูปแบบ "<x" หรือ "≤x" เท่านั้น
หมายเหตุ: ตัวแปลง PDF ทดสอบกับข้อความที่ถอดจากรายงานจริง (ครั้งที่ 8 ของสาละวิน และครั้งที่ 1-4/2569 ของ สคพ.9)
ถ้าหน่วยงานเปลี่ยนรูปแบบตาราง QC จะไม่ผ่านและระบบจะไม่เผยแพร่ข้อมูลผิด

รัน:
    python scripts/05b_watch_networks.py                    # ตรวจเว็บจริง
    python scripts/05b_watch_networks.py --dry-run          # ดูว่าจะอัปเดตอะไร ไม่เขียนไฟล์
    python scripts/05b_watch_networks.py --pdf a.pdf --net mekong_ne --round 5 --month "พฤศจิกายน 2569"
"""
from pathlib import Path
import argparse
import datetime as dt
import calendar
import hashlib
import json
import re
import sys
from urllib.parse import urljoin, urlparse, parse_qs

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
NET = ROOT / "data" / "raw_tables" / "networks"
INCOMING = ROOT / "data" / "incoming"
STATE = ROOT / "data" / "state" / "watch_networks.json"
UA = {"User-Agent": "arsenic-forecast/1.0 (student research; contact in README)"}
TH_MONTH = {"มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4, "พฤษภาคม": 5, "มิถุนายน": 6, "กรกฎาคม": 7,
            "สิงหาคม": 8, "กันยายน": 9, "ตุลาคม": 10, "พฤศจิกายน": 11, "ธันวาคม": 12}
SRC = {"salween": ("https://epo01.pcd.go.th", "/th/information/more/358"),
       "mekong_ne": ("https://epo09.pcd.go.th", "/th/information/more/579")}
VAL = re.compile(r"^(<|≤)?\d+(\.\d+)?$")
SAL_IDS = r"(SAL\d\d|PO01|SAM01|KEB01|PIN01|MOE01|POR01|KON01|YUA01|PY01)"
NE_IDS = ["NK05", "NK06", "NK07", "NK08"]
FY_BASE = 2569   # ปีงบประมาณ 2569 ครั้งที่ 1-4 = รอบ 1-4 ของเครือข่าย mekong_ne; ปีถัดไปนับต่อ (4 ครั้งต่อปี)


# ---------- รายการรายงาน ----------
def list_reports(net, max_pages=4):
    import requests
    from html.parser import HTMLParser

    class A(HTMLParser):
        def __init__(self):
            super().__init__(); self.links = []
        def handle_starttag(self, tag, attrs):
            h = dict(attrs).get("href", "")
            if tag == "a" and ("view/?file=" in h or "download/?file=" in h):
                self.links.append(h)

    host, path = SRC[net]
    out, seen = [], set()
    for p in range(1, max_pages + 1):
        r = requests.get(host + path + ("" if p == 1 else f"/page/{p}"), headers=UA, timeout=60)
        r.raise_for_status()
        a = A(); a.feed(r.text)
        for h in a.links:
            full = urljoin(host + "/", h)
            name = parse_qs(urlparse(full).query).get("n", [""])[0]
            if net == "salween":
                if "สาละวิน" not in name or "ตะกอน" in name:
                    continue
                m = re.search(r"ครั้งที่\s*(\d+)", name)
                if not m: continue
                rnd = int(m.group(1)); s, e = parse_range(name.split("วันที่")[-1]) if "วันที่" in name else (None, None)
            else:
                if "คุณภาพน้ำแหล่งน้ำผิวดิน" not in name:
                    continue
                m = re.search(r"(25\d\d)\s*ครั้งที่\s*(\d+)", name)
                if not m: continue
                rnd = (int(m.group(1)) - FY_BASE) * 4 + int(m.group(2)); s = e = None
            key = (net, rnd)
            if key in seen: continue
            seen.add(key)
            out.append(dict(net=net, round=rnd, title=name, url=full.replace("/view/", "/download/"), start=s, end=e))
    return out


def parse_range(s):
    s = s.replace("–", "-").replace("—", "-").replace("กฤกฎาคม", "กรกฎาคม")
    m = re.search(r"(\d{1,2})\s*(\D*?)\s*-\s*(\d{1,2})\s*(\S+)\s*(25\d\d)", s)
    if not m: return None, None
    d1, mon1, d2, mon2, by = m.groups(); y = int(by) - 543
    m2 = TH_MONTH.get(mon2.strip()); m1 = TH_MONTH.get(mon1.strip(), m2) if mon1.strip() else m2
    if not m2: return None, None
    return dt.date(y - (m1 > m2), m1, int(d1)).isoformat(), dt.date(y, m2, int(d2)).isoformat()


def month_range(text):
    """'ครั้งที่ 4 เดือน สิงหาคม 2569' -> วันแรกและวันสุดท้ายของเดือน (รายงาน สคพ.9 ระบุเพียงเดือน)"""
    t = re.sub(r"(\d)\s+(?=\d)", r"\1", text)   # PDF มักแยกตัวเลขปี เช่น '25 6 9'
    t = re.sub(r"เดื\s*อน", "เดือน", t)
    m = re.search(r"เดือน\s*(\S+)\s*(25\d\d)", t)
    if not m or m.group(1) not in TH_MONTH: return None, None
    y, mo = int(m.group(2)) - 543, TH_MONTH[m.group(1)]
    return dt.date(y, mo, 1).isoformat(), dt.date(y, mo, calendar.monthrange(y, mo)[1]).isoformat()


# ---------- แปลงข้อความในตาราง ----------
def pdf_lines(pdf):
    import pdfplumber
    pages = []
    with pdfplumber.open(pdf) as doc:
        for pg in doc.pages:
            words = pg.extract_words(keep_blank_chars=False, use_text_flow=False, x_tolerance=1.5, y_tolerance=2)
            rows = {}
            for w in words:
                k = round(w["top"] / 3)
                rows.setdefault(k, []).append(w)
            lines = [" ".join(x["text"] for x in sorted(v, key=lambda z: z["x0"])) for _, v in sorted(rows.items())]
            pages.append(lines)
    return pages


def merge_split_numbers(tok, expected):
    """PDF ของ สคพ.9 มักพิมพ์ '0.00 2' หรือ '≤ 0.01' แยกกัน รวมกลับจนเหลือจำนวนคอลัมน์ที่คาดไว้"""
    tok = [t.replace(",", "") for t in tok]
    out = []
    for t in tok:
        if out and out[-1] in ("≤", "<"):
            out[-1] += t
        else:
            out.append(t)
    i = 0
    while len(out) > expected and i < len(out) - 1:
        if re.fullmatch(r"\d+\.\d*", out[i]) and re.fullmatch(r"\d{1,2}", out[i + 1]):
            out[i] += out[i + 1]; del out[i + 1]
        else:
            i += 1
    return out


def norm_val(t):
    t = t.strip()
    if t in ("-", "", "ND"): return t or "-"
    t = t.replace("≤", "≤").replace(" ", "")
    if t.startswith("≤") or t.startswith("<"):
        return t[0] + f"{float(t[1:]):.3f}"
    return t


def parse_salween_as(pages, n_rounds):
    """หาหน้าตารางสารหนูภาคผนวก ข แล้วอ่านแถวของทุกสถานี -> DataFrame กว้าง R01..Rn"""
    for lines in pages:
        head = " ".join(lines[:6])
        if "สารหนู" not in head or "ตาราง" not in head:
            continue
        rows = {}
        for ln in lines:
            m = re.match(SAL_IDS + r"\b(.*)$", ln.replace(" ", " ").strip().replace("P Y0 1", "PY01"))
            if not m: continue
            vals = [norm_val(t) for t in re.findall(r"<\s*\d+\.\d+|≤\s*\d+\.\d+|\d+\.\d+|(?<!\S)-(?!\S)", m.group(2))]
            vals = [v.replace(" ", "") for v in vals]
            if len(vals) == n_rounds - 1 and m.group(1) == "SAL02":   # SAL02 ในต้นฉบับขาดหนึ่งช่องหลังครั้งที่ 1
                vals.append("-")
            if len(vals) == n_rounds:
                rows[m.group(1)] = vals
        if len(rows) >= 10:
            return pd.DataFrame.from_dict(rows, orient="index", columns=[f"R{i:02d}" for i in range(1, n_rounds + 1)])
    return None


def parse_epo09(pages):
    """ตารางที่ 2 (โลหะหนัก, As เป็นคอลัมน์ที่ 9 จาก 11) และตารางที่ 1 (ความขุ่นเป็นคอลัมน์ที่ 2) ของ NK05-NK08"""
    As, turb, head = {}, {}, ""
    for lines in pages:
        txt = " ".join(lines)
        if "ครั้ง" in txt and re.search(r"เดื\s*อน", txt) and not head:
            head = txt
        for ln in lines:
            m = re.search(r"(?:^|\s)(NK0\s?[5-8])\s+(.*)$", ln.strip())
            if not m: continue
            sid = m.group(1).replace(" ", ""); tok = m.group(2).split()
            if "ตารางที่ 2" in txt:
                t = merge_split_numbers(tok, 11)
                if len(t) >= 9: As[sid] = norm_val(t[8])
            elif "ตารางที่ 1" in txt or "Turbidity" in txt:
                t = merge_split_numbers(tok, 16)
                if len(t) >= 2 and re.fullmatch(r"\d+(\.\d+)?", t[1]): turb[sid] = t[1]
    return As, turb, head


# ---------- เขียนไฟล์ ----------
def latest(pattern):
    fs = sorted(NET.glob(pattern), key=lambda p: int(re.search(r"R01-R(\d+)", p.name).group(1)))
    return fs[-1] if fs else None


def agreement(new, old):
    pairs = [(s, c) for s in old.index for c in old.columns if s in new.index and c in new.columns and str(old.loc[s, c]) != "-"]
    if not pairs: return 0.0
    f = lambda v: str(v).replace("<0.01", "<0.010").strip()
    return sum(f(new.loc[s, c]) == f(old.loc[s, c]) for s, c in pairs) / len(pairs)


def add_round(net, rnd, start, end, status, src, note=""):
    p = NET / f"{net}_rounds.csv"; r = pd.read_csv(p, dtype=str)
    r = r[r["round"].astype(int) != rnd]
    r = pd.concat([r, pd.DataFrame([dict(network=net, media="water", round=rnd, sample_start=start, sample_end=end,
                                         date_status=status, source_url=src, note=note or "เพิ่มโดย 05b_watch_networks.py")])])
    r.sort_values("round", key=lambda x: x.astype(int)).to_csv(p, index=False)


def process_salween(pdf, rnd, start, end, src, dry):
    pages = pdf_lines(pdf)
    new = parse_salween_as(pages, rnd)
    if new is None:
        print("QC ไม่ผ่าน: ไม่พบตารางสารหนูสาละวิน"); return 2
    old_f = latest("salween_water_as_R01-R*_epo01.csv"); old = pd.read_csv(old_f, dtype=str).set_index("station_id")
    ag = agreement(new, old); n_new = int((new[f"R{rnd:02d}"] != "-").sum())
    print(f"สาละวินครั้งที่ {rnd}: ตรงกับข้อมูลเดิม {ag:.1%}, ค่าครั้งใหม่ {n_new} จุด")
    if ag < 0.98 or n_new < 3:
        print("QC ไม่ผ่าน ไม่เขียนทับ"); return 2
    if dry: return 0
    new.index.name = "station_id"
    new.to_csv(NET / f"salween_water_as_R01-R{rnd:02d}_epo01.csv")
    add_round("salween", rnd, start, end, "official" if start else "unknown", src)
    return 0


def process_mekong_ne(pdf, rnd, src, dry, month_text=None):
    pages = pdf_lines(pdf)
    As, turb, head = parse_epo09(pages)
    start, end = month_range(month_text or head)
    ok = [s for s in NE_IDS if s in As and VAL.match(As[s].replace("≤", "<"))]
    print(f"โขงอีสานรอบ {rnd} ({start}): As {As} ความขุ่น {turb}")
    if len(ok) < 3 or not start:
        print("QC ไม่ผ่าน ไม่เขียนทับ"); return 2
    if dry: return 0
    for kind, d in (("water_as", As), ("turbidity", turb)):
        f = latest(f"mekong_ne_{kind}_R01-R*_epo09.csv"); t = pd.read_csv(f, dtype=str).set_index("station_id")
        col = f"R{rnd:02d}"
        for s in NE_IDS:
            t.loc[f"E9-{s}", col] = d.get(s, "-")
        t = t.reindex(columns=sorted(t.columns, key=lambda c: int(c[1:]))).fillna("-")
        t.to_csv(NET / f"mekong_ne_{kind}_R01-R{max(rnd, int(f.name.split('-R')[2][:2])):02d}_epo09.csv")
    add_round("mekong_ne", rnd, start, end, "month_only", src, "รายงานระบุเพียงเดือน")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf"); ap.add_argument("--net", choices=list(SRC)); ap.add_argument("--round", type=int)
    ap.add_argument("--dates", default=""); ap.add_argument("--month", default=""); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    INCOMING.mkdir(parents=True, exist_ok=True); STATE.parent.mkdir(parents=True, exist_ok=True)
    state = json.loads(STATE.read_text()) if STATE.exists() else {"processed": {}}
    if a.pdf:
        if a.net == "salween":
            s, e = parse_range(a.dates) if a.dates else (None, None)
            sys.exit(process_salween(Path(a.pdf), a.round, s, e, "local:" + a.pdf, a.dry_run))
        sys.exit(process_mekong_ne(Path(a.pdf), a.round, "local:" + a.pdf, a.dry_run, ("เดือน " + a.month) if a.month else None))

    import requests
    rc = 0
    for net in SRC:
        have = max(pd.read_csv(NET / f"{net}_rounds.csv")["round"].astype(int))
        try:
            reps = [r for r in list_reports(net) if r["round"] > have]
        except Exception as ex:   # เว็บหน่วยงานล่ม: ข้ามรอบนี้ ข้อมูลเดิมยังใช้ได้
            print(f"{net}: อ่านหน้ารายการไม่ได้ ({ex})"); continue
        if not reps:
            print(f"{net}: ไม่มีรายงานใหม่ (มีถึงรอบ {have})"); continue
        for rep in sorted(reps, key=lambda r: r["round"]):
            resp = requests.get(rep["url"], headers=UA, timeout=180); resp.raise_for_status()
            if not resp.content.startswith(b"%PDF"):
                print("ไม่ใช่ไฟล์ PDF ข้าม:", rep["title"]); continue
            sha = hashlib.sha256(resp.content).hexdigest()
            pdf = INCOMING / f"{net}_R{rep['round']:02d}_{sha[:10]}.pdf"; pdf.write_bytes(resp.content)
            src = f"{rep['title']} {SRC[net][0] + SRC[net][1]}"
            r = (process_salween(pdf, rep["round"], rep["start"], rep["end"], src, a.dry_run) if net == "salween"
                 else process_mekong_ne(pdf, rep["round"], src, a.dry_run))
            rc = max(rc, r)
            if r == 0:
                state["processed"][f"{net}_{rep['round']}"] = dict(sha256=sha, title=rep["title"], at=dt.datetime.now().isoformat(timespec="seconds"))
    if not a.dry_run:
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    sys.exit(rc)


if __name__ == "__main__":
    main()
