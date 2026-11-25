"""run_all.py  ขั้นตอนคำนวณใหม่เมื่อได้รับข้อมูลใหม่จากแหล่งที่ยืนยันแล้ว
1) build  -> 2) QC gate (ถ้าไม่ผ่าน หยุด ไม่เผยแพร่)  -> 3) forecast
รันเฉพาะเมื่อไฟล์ใน data/raw_tables เปลี่ยน (เทียบ hash กับครั้งก่อน) ใช้ --force เพื่อบังคับ

รัน:  python scripts/run_all.py [--force]
"""
from pathlib import Path
import hashlib
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / ".last_raw_hash"


def raw_hash():
    h = hashlib.sha256()
    for p in sorted((ROOT / "data" / "raw_tables").rglob("*.csv")):   # รวมเครือข่ายสาละวินและโขงอีสานใน networks/
        h.update(str(p.relative_to(ROOT)).encode()); h.update(p.read_bytes())
    return h.hexdigest()


def run(script, *args):
    print(f"== {script}")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *args])
    if r.returncode != 0:
        sys.exit(f"หยุด: {script} ไม่ผ่าน (exit {r.returncode}) ไม่อัปเดตผลพยากรณ์")


def main():
    new = raw_hash()
    old = STATE.read_text().strip() if STATE.exists() else ""
    if new == old and "--force" not in sys.argv:
        print("ไม่มีข้อมูลใหม่ ไม่ต้องคำนวณใหม่")
        return
    run("01_build_dataset.py")
    run("02_validate_dataset.py")
    run("03_forecast_baseline.py")
    STATE.write_text(new)
    print("อัปเดตผลพยากรณ์แล้ว: data/forecast/forecast_latest.json")


if __name__ == "__main__":
    main()
