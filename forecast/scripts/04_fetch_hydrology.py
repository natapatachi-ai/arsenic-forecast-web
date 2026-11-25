"""04_fetch_hydrology.py  (แม่แบบ ให้รันบนเครื่องผู้ใช้ที่ต่ออินเทอร์เน็ต)
ดึงข้อมูลระดับน้ำ/อัตราการไหลและฝน เพื่อใช้เป็นตัวแปร Q, P ในแบบจำลอง M2 และ EEMD

สถานะ: [ต้องกำหนด] รหัสสถานีวัดน้ำของกรมชลประทานบนแม่น้ำกก/สาย/รวก ยังไม่ได้ยืนยัน
  - ค้นรหัสสถานีจาก https://hydro-1.rid.go.th (สำนักงานชลประทานที่ 1) หรือคลังข้อมูลน้ำแห่งชาติ https://www.thaiwater.net
  - ใส่รหัสใน STATIONS ด้านล่าง แล้วรัน:  python scripts/04_fetch_hydrology.py --year 2026 --month 7

ผลลัพธ์:  data/hydrology/rid_<code>_<yyyy>-<mm>.csv  (แต่ละไฟล์เก็บ URL และเวลาที่ดึงไว้ในคอลัมน์ source_url, fetched_at)
"""
from pathlib import Path
import argparse
import datetime as dt
import io

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "hydrology"

# ตัวอย่างรูปแบบ URL ของกรมชลประทาน (ปี ค.ศ.) ตรวจสอบว่ายังใช้ได้ก่อนใช้งานจริง
RID_URL = "http://hydro-1.rid.go.th/Data/HD-04/houly/water_today_search.php?storage={code}&yy={yy}&mm={mm:02d}"

STATIONS = {
    # "รหัสสถานี": "คำอธิบาย / สถานีคุณภาพน้ำ คพ. ที่ใกล้ที่สุด",
    # "P.1": "ตัวอย่างรูปแบบรหัส (ปิง เชียงใหม่) ไม่ใช่แม่น้ำกก",
}


def fetch_rid(code, yy, mm):
    import requests
    import pandas as pd
    url = RID_URL.format(code=code, yy=yy, mm=mm)
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    tables = pd.read_html(io.StringIO(r.text))
    df = max(tables, key=len)  # ตารางที่ใหญ่ที่สุดคือข้อมูลรายชั่วโมง
    df["station_code"] = code
    df["source_url"] = url
    df["fetched_at"] = dt.datetime.now().isoformat(timespec="seconds")
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--month", type=int, required=True)
    a = ap.parse_args()
    if not STATIONS:
        raise SystemExit("[ต้องกำหนด] ใส่รหัสสถานีใน STATIONS ก่อน")
    OUT.mkdir(parents=True, exist_ok=True)
    for code in STATIONS:
        df = fetch_rid(code, a.year, a.month)
        p = OUT / f"rid_{code}_{a.year}-{a.month:02d}.csv"
        df.to_csv(p, index=False)
        print("saved", p, len(df), "rows")


if __name__ == "__main__":
    main()
