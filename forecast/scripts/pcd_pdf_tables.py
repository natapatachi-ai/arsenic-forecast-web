"""pcd_pdf_tables.py
ถอดตารางภาคผนวก ข จากรายงาน PDF ของกรมควบคุมมลพิษ (สำนักงานสิ่งแวดล้อมและควบคุมมลพิษที่ 1)
ใช้ตำแหน่งของคำในหน้า (x, y) จาก pdfplumber:
  - แถว = ระดับ y ของรหัสสถานี (KK01, SA02, ...)
  - คอลัมน์ = ตำแหน่ง x ของเลขครั้งที่ในหัวตาราง (1, 2, ..., 24)

ใช้กับทั้งรายงานคุณภาพน้ำ (mg/L, NTU) และรายงานตะกอนดิน (mg/kg)

ตัวอย่าง:
    from pcd_pdf_tables import extract_tables
    tabs = extract_tables("report.pdf")            # {(ชื่อพารามิเตอร์, ปี): DataFrame}
"""
import re
from collections import defaultdict
import pandas as pd

STATION = re.compile(r"(KK|FA|KO|LA|SU|SA|RU|NK)\d{2}")
VALUE = re.compile(r"^(<\s*\d*\.?\d+|\d[\d,]*\.?\d*|-|ND)$")
PARAMS = ["ความขุ่น", "สารหนู", "ตะกั่ว", "ปรอท", "ทองแดง", "สังกะสี", "นิกเกิล", "แคดเมียม",
          "แมงกานีส", "โครเมียม"]
PARAM_EN = {"ความขุ่น": "turbidity", "สารหนู": "As", "ตะกั่ว": "Pb", "ปรอท": "Hg", "ทองแดง": "Cu",
            "สังกะสี": "Zn", "นิกเกิล": "Ni", "แคดเมียม": "Cd", "แมงกานีส": "Mn", "โครเมียม": "Cr"}


def _group_rows(words, tol=2.0):
    rows = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        for r in rows:
            if abs(r["y"] - w["top"]) <= tol:
                r["w"].append(w)
                break
        else:
            rows.append({"y": w["top"], "w": [w]})
    return rows


def _merge_digits(ws):
    cols = []
    for w in sorted(ws, key=lambda w: w["x0"]):
        if cols and w["x0"] - cols[-1]["x1"] < 1.5:
            cols[-1]["text"] += w["text"]
            cols[-1]["x1"] = w["x1"]
        else:
            cols.append({"text": w["text"], "x0": w["x0"], "x1": w["x1"], "top": w["top"]})
    return cols


def _header_columns(words, table_top):
    """หาแถวหัวตาราง: แถวของเลขครั้งที่ที่เรียงต่อเนื่อง (n, n+1, n+2, ...) ยาวที่สุด"""
    nums = [w for w in words if re.fullmatch(r"\d{1,2}", w["text"]) and w["top"] > table_top]
    best = []
    for r in _group_rows(nums, tol=1.5):
        cols = _merge_digits(r["w"])
        seq = [int(c["text"]) for c in cols]
        run, cur = [], [cols[0]] if cols else []
        for a, b, c in zip(seq, seq[1:], cols[1:]):
            if b == a + 1:
                cur.append(c)
            else:
                run = max(run, cur, key=len)
                cur = [c]
        run = max(run, cur, key=len)
        if len(run) > len(best):
            best = run
    return [(int(c["text"]), (c["x0"] + c["x1"]) / 2, c["top"]) for c in best]


def parse_page(page):
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False, x_tolerance=1.5)
    text = " ".join(w["text"] for w in words)
    head = "".join((page.extract_text() or "").split("\n")[:6]).replace(" ", "")
    # เฉพาะหน้าตารางภาคผนวก: "ตารางแสดงผลการตรวจวัดคุณภาพ..." ตามด้วยชื่อพารามิเตอร์
    if "ตารางแสดงผลการตรวจวัดคุณภาพ" not in head or not STATION.search(text):
        return None
    tail = head.split("พารามิเตอร์", 1)[-1]
    found = [(tail.find(p), p) for p in PARAMS if p in tail]
    if not found:
        return None
    param = min(found)[1]
    year = re.search(r"25\s*6\s*\d", text)
    year = year.group(0).replace(" ", "") if year else ""
    cols = _header_columns(words, 0)
    if len(cols) < 3:
        return None
    hdr_y = max(c[2] for c in cols)
    x_first = min(c[1] for c in cols)
    gap = (cols[-1][1] - cols[0][1]) / max(len(cols) - 1, 1)
    # ป้ายสถานี (อาจถูกแยกเป็นหลายคำ เช่น 'NK' '01')
    left = [w for w in words if w["x1"] < x_first - gap / 2 and w["top"] > hdr_y]
    stations = []
    for r in _group_rows(left, tol=1.5):
        label = "".join(w["text"] for w in sorted(r["w"], key=lambda w: w["x0"]))
        m = STATION.search(label)
        if m:
            stations.append((m.group(0), r["y"]))
    vals = [w for w in words if w["x0"] >= x_first - gap * 0.6 and w["top"] > hdr_y + 2
            and VALUE.match(w["text"].replace(" ", ""))]
    cells = defaultdict(list)
    for v in vals:
        sid, dy = min(((s, abs(y - v["top"])) for s, y in stations), key=lambda t: t[1], default=(None, 99))
        if sid is None or dy > 6:
            continue
        xc = (v["x0"] + v["x1"]) / 2
        rnd = min(cols, key=lambda c: abs(c[1] - xc))[0]
        cells[(sid, rnd)].append(v)
    out = {}
    for sid, _ in stations:
        out[sid] = {f"R{r:02d}": "".join(w["text"] for w in sorted(cells.get((sid, r), []), key=lambda w: w["x0"]))
                    .replace(",", "") or "-" for r, _, _ in cols}
    df = pd.DataFrame.from_dict(out, orient="index")
    df.index.name = "station_id"
    return PARAM_EN[param], year, df


def extract_tables(pdf_path):
    import pdfplumber
    tabs = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            res = parse_page(page)
            if res is None:
                continue
            p, y, df = res
            key = (p, "")
            tabs[key] = df if key not in tabs else tabs[key].combine_first(df)
    return tabs


def combine_years(tabs, param):
    """รวมตารางปี 2568 และ 2569 ของพารามิเตอร์เดียวกันเป็นตารางกว้าง R01..Rn"""
    parts = [df for (p, _), df in sorted(tabs.items()) if p == param]
    if not parts:
        return None
    out = pd.concat(parts, axis=1)
    out = out.loc[:, ~out.columns.duplicated()]
    return out[sorted(out.columns)]
