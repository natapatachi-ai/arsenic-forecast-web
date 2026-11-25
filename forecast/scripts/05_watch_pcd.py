"""05_watch_pcd.py  ตัวเฝ้าแหล่งข้อมูล (ขั้นแรกของระบบอัปเดตอัตโนมัติ)

ทำงานดังนี้
 1. อ่านหน้ารายการเอกสารของ สสภ.1 (กรมควบคุมมลพิษ) https://epo01.pcd.go.th/th/information/more/358
 2. หารายงานแม่น้ำกก-สาย-รวก-โขง ที่ "ครั้งที่" ใหม่กว่าข้อมูลที่มีอยู่
 3. ดาวน์โหลด PDF -> ถอดตารางภาคผนวก ข ด้วย pcd_pdf_tables.py
 4. QC: ค่ารอบเก่าในฉบับใหม่ต้องตรงกับข้อมูลเดิมอย่างน้อย 98% และรอบใหม่ต้องมีค่าอย่างน้อย 10 จุด
    ถ้าไม่ผ่าน จะไม่เขียนทับข้อมูล (ข้อมูลเก่ายังใช้ได้) และจบด้วย exit code 2
 5. เขียนไฟล์ใหม่ใน data/raw_tables และเพิ่มวันที่ของรอบใน data/processed/rounds.csv
    จากนั้น run_all.py จะเห็นว่า hash เปลี่ยน แล้วคำนวณใหม่ทั้งหมด

รัน:
    python scripts/05_watch_pcd.py               # ตรวจเว็บจริง
    python scripts/05_watch_pcd.py --pdf a.pdf --kind sediment --round 14 --dates "6 - 9 พฤศจิกายน 2569"
                                                 # ใช้ไฟล์ PDF ที่ดาวน์โหลดเอง
"""
from pathlib import Path
import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from urllib.parse import urljoin, urlparse, parse_qs

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pcd_pdf_tables import extract_tables, combine_years  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw_tables"
PROC = ROOT / "data" / "processed"
INCOMING = ROOT / "data" / "incoming"
STATE = ROOT / "data" / "state" / "watch_state.json"
LIST_URL = "https://epo01.pcd.go.th/th/information/more/358"
UA = {"User-Agent": "arsenic-forecast/1.0 (student research; contact in README)"}
TH_MONTH = {"มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4, "พฤษภาคม": 5, "มิถุนายน": 6, "กรกฎาคม": 7,
            "สิงหาคม": 8, "กันยายน": 9, "ตุลาคม": 10, "พฤศจิกายน": 11, "ธันวาคม": 12}
WATER_METALS = ["Pb", "Hg", "Cu", "Zn", "Ni", "Cd"]
SED_METALS_TH = {"As": "สารหนู", "Cd": "แคดเมียม", "Mn": "แมงกานีส", "Ni": "นิกเกิล", "Pb": "ตะกั่ว",
                 "Zn": "สังกะสี", "Cu": "ทองแดง", "Hg": "ปรอท", "Cr": "โครเมียม"}


def parse_thai_range(s):
    """'26 – 30 ตุลาคม 2569' หรือ '27 เมษายน - 1 พฤษภาคม 2569' -> (start, end) แบบ ค.ศ."""
    s = s.replace("–", "-").replace("—", "-")
    m = re.search(r"(\d{1,2})\s*(\D*?)\s*-\s*(\d{1,2})\s*(\S+)\s*(25\d\d)", s)
    if not m:
        return None, None
    d1, mon1, d2, mon2, by = m.groups()
    y = int(by) - 543
    m2 = TH_MONTH.get(mon2.strip())
    m1 = TH_MONTH.get(mon1.strip(), m2) if mon1.strip() else m2
    if not m2:
        return None, None
    y1 = y - 1 if m1 > m2 else y
    return dt.date(y1, m1, int(d1)).isoformat(), dt.date(y, m2, int(d2)).isoformat()


def list_reports(max_pages=3):
    import requests
    from html.parser import HTMLParser

    class A(HTMLParser):
        def __init__(self):
            super().__init__(); self.links = []
        def handle_starttag(self, tag, attrs):
            h = dict(attrs).get("href", "")
            if tag == "a" and "view/?file=" in h:
                self.links.append(h)

    out = []
    for p in range(1, max_pages + 1):
        url = LIST_URL if p == 1 else f"{LIST_URL}/page/{p}"
        r = requests.get(url, headers=UA, timeout=60)
        r.raise_for_status()
        a = A(); a.feed(r.text)
        for h in a.links:
            full = urljoin("https://epo01.pcd.go.th/", h)
            name = parse_qs(urlparse(full).query).get("n", [""])[0]
            if "กก" not in name:
                continue
            kind = "sediment" if "ตะกอน" in name else ("water" if "น้ำ" in name else None)
            rnd = re.search(r"ครั้งที่\s*(\d+)", name)
            if kind and rnd:
                s, e = parse_thai_range(name.split("วันที่")[-1]) if "วันที่" in name else (None, None)
                out.append(dict(kind=kind, round=int(rnd.group(1)), title=name, url=full, start=s, end=e))
    return out


def latest_file(pattern):
    files = sorted(RAW.glob(pattern), key=lambda p: int(re.search(r"R(\d+)_pcd", p.name).group(1)))
    return files[-1] if files else None


def agreement(new_df, old_df, cols):
    both = [(s, c) for s in old_df.index for c in cols if s in new_df.index and c in new_df.columns]
    if not both:
        return 0.0
    same = sum(str(new_df.loc[s, c]).strip() == str(old_df.loc[s, c]).strip() for s, c in both)
    return same / len(both)


def process_water(pdf, rnd, start, end, dry):
    tabs = extract_tables(pdf)
    asn = combine_years(tabs, "As")
    tur = combine_years(tabs, "turbidity")
    if asn is None or tur is None:
        raise SystemExit("QC: ไม่พบตารางสารหนูหรือความขุ่นในภาคผนวก")
    col = f"R{rnd:02d}"
    old = pd.read_csv(latest_file("water_as_R01-R*_pcd.csv"), dtype=str).set_index("station_id")
    agr = agreement(asn, old, list(old.columns))
    n_new = (asn[col] != "-").sum() if col in asn.columns else 0
    print(f"water R{rnd}: agreement with old rounds = {agr:.1%}, stations with new value = {n_new}")
    if agr < 0.98 or n_new < 10:
        print("QC ไม่ผ่าน ไม่เขียนทับข้อมูล"); sys.exit(2)
    if dry:
        return
    asn.index.name = "station_id"
    asn.to_csv(RAW / f"water_as_R01-R{rnd:02d}_pcd.csv")
    tur.index.name = "station_id"
    tur[[c for c in tur.columns if int(c[1:]) >= 11]].to_csv(RAW / f"turbidity_R11-R{rnd:02d}_pcd.csv")
    lines = ["# ถอดอัตโนมัติด้วย 05_watch_pcd.py จาก " + str(pdf)]
    for m in WATER_METALS:
        t = combine_years(tabs, m)
        if t is None:
            continue
        for yr, cols in (("2568", [c for c in t.columns if int(c[1:]) <= 14]),
                         ("2569", [c for c in t.columns if int(c[1:]) >= 15])):
            lines.append(f"#{m} {yr}")
            lines.append("station;" + ";".join(f"R{int(c[1:])}" for c in cols))
            lines += [s + ";" + ";".join(t.loc[s, c] for c in cols) for s in t.index]
    (RAW / f"water_metals_R01-R{rnd:02d}_pcd.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    add_round("water", rnd, start, end, str(pdf))


def process_sediment(pdf, rnd, start, end, dry):
    tabs = extract_tables(pdf)
    asn = combine_years(tabs, "As")
    col = f"R{rnd:02d}"
    old = pd.read_csv(latest_file("sediment_as_R01-R*_pcd.csv"), dtype=str).set_index("station_id")
    agr = agreement(asn, old, list(old.columns))
    n_new = (asn[col] != "-").sum() if col in asn.columns else 0
    print(f"sediment R{rnd}: agreement with old rounds = {agr:.1%}, stations with new value = {n_new}")
    if agr < 0.98 or n_new < 10:
        print("QC ไม่ผ่าน ไม่เขียนทับข้อมูล"); sys.exit(2)
    if dry:
        return
    asn.index.name = "station_id"
    asn.to_csv(RAW / f"sediment_as_R01-R{rnd:02d}_pcd.csv")
    rows = []
    for p, th in SED_METALS_TH.items():
        t = combine_years(tabs, p)
        if t is None:
            continue
        for s in t.index:
            for c in t.columns:
                rows.append(dict(parameter_en=p, parameter=th, station_id=s, round=int(c[1:]), value_reported=t.loc[s, c]))
    pd.DataFrame(rows).to_csv(RAW / f"sediment_metals_R01-R{rnd:02d}_pcd.csv", index=False)
    add_round("sediment", rnd, start, end, str(pdf))


def add_round(media, rnd, start, end, src):
    r = pd.read_csv(PROC / "rounds.csv", dtype=str)
    i = (r.media == media) & (r["round"] == str(rnd))
    row = dict(media=media, round=str(rnd), sample_start=start or "", sample_end=end or "",
               date_status="official" if start else "unknown", source_url=src, note="เพิ่มโดย 05_watch_pcd.py")
    if i.any():
        for k, v in row.items():
            r.loc[i, k] = v
    else:
        r = pd.concat([r, pd.DataFrame([row])], ignore_index=True)
    r.to_csv(PROC / "rounds.csv", index=False)


def max_round(pattern):
    f = latest_file(pattern)
    return int(re.search(r"R(\d+)_pcd", f.name).group(1)) if f else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf"); ap.add_argument("--kind", choices=["water", "sediment"])
    ap.add_argument("--round", type=int); ap.add_argument("--dates", default="")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    INCOMING.mkdir(parents=True, exist_ok=True); STATE.parent.mkdir(parents=True, exist_ok=True)
    state = json.loads(STATE.read_text()) if STATE.exists() else {"processed": {}}

    if a.pdf:
        s, e = parse_thai_range(a.dates) if a.dates else (None, None)
        (process_water if a.kind == "water" else process_sediment)(Path(a.pdf), a.round, s, e, a.dry_run)
        return

    import requests
    have = {"water": max_round("water_as_R01-R*_pcd.csv"), "sediment": max_round("sediment_as_R01-R*_pcd.csv")}
    reports = list_reports()
    new = sorted([r for r in reports if r["round"] > have[r["kind"]]], key=lambda r: (r["kind"], r["round"]))
    if not new:
        print("ไม่มีรายงานใหม่", have); return
    for rep in new:
        resp = requests.get(rep["url"], headers=UA, timeout=120)
        resp.raise_for_status()
        if not resp.content.startswith(b"%PDF"):
            print("ไม่ใช่ไฟล์ PDF ข้าม:", rep["title"]); continue
        sha = hashlib.sha256(resp.content).hexdigest()
        pdf = INCOMING / f"{rep['kind']}_R{rep['round']:02d}_{sha[:10]}.pdf"
        pdf.write_bytes(resp.content)
        print("ดาวน์โหลด", rep["title"], len(resp.content), "bytes")
        (process_water if rep["kind"] == "water" else process_sediment)(pdf, rep["round"], rep["start"], rep["end"], a.dry_run)
        state["processed"][f"{rep['kind']}_{rep['round']}"] = dict(sha256=sha, title=rep["title"],
                                                                   at=dt.datetime.now().isoformat(timespec="seconds"))
    if not a.dry_run:
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
