# วิธีรันโค้ด (Windows / macOS / Linux, Python 3.10 ขึ้นไป)

```bash
pip install -r requirements.txt pdfplumber matplotlib
python scripts/run_all.py --force      # 01 build -> 02 QC -> 03 forecast
python scripts/06_export_site.py       # ไฟล์ JSON สำหรับหน้าเว็บ -> ../web/data/
python scripts/07_figures.py           # รูปผลลัพธ์ -> results/
python scripts/05_watch_pcd.py         # ตรวจรายงานใหม่บนเว็บ คพ. (ต้องต่ออินเทอร์เน็ต)
```

| ไฟล์ | หน้าที่ |
|---|---|
| scripts/01_build_dataset.py | แปลงตารางดิบ (data/raw_tables) เป็นตารางยาวพร้อมข้อมูลเซ็นเซอร์ |
| scripts/02_validate_dataset.py | QC gate ถ้าไม่ผ่านจะหยุดและไม่เผยแพร่ |
| scripts/03_forecast_baseline.py | แบบจำลอง censored log-AR(1) + Tobit ความขุ่น + ทดสอบย้อนหลัง |
| scripts/04_fetch_hydrology.py | แม่แบบดึงระดับน้ำกรมชลประทาน (ต้องใส่รหัสสถานี) |
| scripts/05_watch_pcd.py | เฝ้าเว็บ คพ. ดาวน์โหลดรายงานใหม่ ถอดตาราง และตรวจ QC |
| scripts/pcd_pdf_tables.py | ตัวถอดตารางภาคผนวก ข จาก PDF ด้วยพิกัดคำ |
| scripts/06_export_site.py | ส่งออก JSON ให้หน้าเว็บ |
| scripts/07_figures.py | สร้างรูปผลลัพธ์ |
| scripts/run_all.py | ลำดับการรัน และคำนวณใหม่เมื่อข้อมูลดิบเปลี่ยน |
| .github/workflows/update-forecast.yml | รันอัตโนมัติทุก 6 ชั่วโมงบน GitHub Actions |
| tools/browser_pdf_extract.js | เครื่องมือที่ใช้ถอดรายงานน้ำครั้งที่ 24 ในเบราว์เซอร์ (ใช้ครั้งเดียว) |
| tools/parse_pdftotext_tables.py | เครื่องมือที่ใช้ถอดตารางตะกอนรอบ 12–13 (ใช้ครั้งเดียว) |
| config/parameters.json | ค่ามาตรฐาน ค่าคงที่เคมี และพารามิเตอร์แบบจำลอง |

## อัปเดตเรียลไทม์ (ทุกเครือข่าย) — ปรับปรุง 24 พ.ย. 2569
1. สร้าง repository บน GitHub แล้วอัปโหลดโฟลเดอร์ทั้งหมด (รวม `.github/workflows/update-forecast.yml`)
2. Settings → Pages → Source = **GitHub Actions**
3. Settings → Actions → General → Workflow permissions = **Read and write**
4. แท็บ Actions → update-forecast → **Run workflow** หนึ่งครั้งเพื่อทดสอบ
หลังจากนั้นระบบทำงานเองทุก 6 ชั่วโมง:
- `05_watch_pcd.py` เฝ้ารายงานแม่น้ำกก–สาย–รวก–โขง (สคพ.1)
- `05b_watch_networks.py` เฝ้ารายงานแม่น้ำสาละวิน (สคพ.1) และแม่น้ำโขงภาคอีสาน (สคพ.9)
- ถ้าพบรายงานใหม่และผ่าน QC → `run_all.py` คำนวณใหม่ → `06_export_site.py` → เผยแพร่ GitHub Pages
- หน้าเว็บที่เปิดค้างไว้จะตรวจ `data/meta.json` ทุก 10 นาที ถ้ามีผลใหม่จะขึ้นแถบ "โหลดข้อมูลใหม่"
ทดสอบตัวแปลง PDF กับไฟล์ที่ดาวน์โหลดเอง (แนะนำให้ทำครั้งแรก):
    python scripts/05b_watch_networks.py --pdf รายงานสาละวินครั้งที่8.pdf --net salween --round 8 --dates "8 - 10 กันยายน 2569" --dry-run
    python scripts/05b_watch_networks.py --pdf รายงาน30สถานีครั้งที่4.pdf --net mekong_ne --round 4 --dry-run
