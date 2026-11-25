# เว็บพยากรณ์สารหนูในแม่น้ำ

```
arsenic-forecast-web/
├── web/        หน้าเว็บ (index.html + data/*.json) — เว็บ static ไม่ต้อง build
├── forecast/   โค้ดพยากรณ์ (Python) + ข้อมูลดิบ ข้อมูลที่ประมวลผลแล้ว และผลลัพธ์
├── .vscode/    ตั้งค่า VS Code (Live Server, tasks)
└── .github/    อัปเดตอัตโนมัติทุก 6 ชั่วโมงบน GitHub Actions + GitHub Pages
```

## เปิดเว็บใน VS Code
1. File → Open Folder… เลือกโฟลเดอร์ `arsenic-forecast-web`
2. ติดตั้งส่วนขยาย **Live Server** (VS Code จะเสนอให้เอง)
3. เปิด `web/index.html` แล้วกด **Go Live** มุมขวาล่าง

หรือ Terminal → Run Task… → **4. เปิดเว็บ** แล้วเข้า http://localhost:8000
(ดับเบิลคลิก index.html ตรง ๆ ไม่ได้ เพราะหน้าเว็บต้องโหลดไฟล์ใน `data/`)

## รันโค้ดพยากรณ์
Terminal → Run Task…
1. **ติดตั้งไลบรารี Python** (ครั้งแรกครั้งเดียว ต้องมี Python 3.10 ขึ้นไป)
2. **พยากรณ์ใหม่ + ส่งข้อมูลให้เว็บ** → อัปเดต `forecast/data/forecast/` และ `web/data/`
3. **สร้างรูปผลลัพธ์** → `forecast/results/`

รายละเอียดแต่ละสคริปต์ดูที่ `forecast/RUN.md` และ `forecast/README.md`
