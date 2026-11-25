# พจนานุกรมข้อมูล (Data Dictionary)

## หลักการ
- ตารางทุกตารางเป็นตารางยาว: 1 แถวต่อ 1 ค่าตรวจวัด (สถานี × รอบ × สื่อ)
- ทุกแถวมีวันที่เก็บตัวอย่าง (`sample_start`, `sample_end`, `t_mid`) และแหล่งที่มา (`source_url`)
- ค่าที่ต่ำกว่าขีดจำกัดการตรวจวัด ห้ามแทนด้วยตัวเลขใด ให้ใช้ `value_low`/`value_high` และ `censor` แทน
- `is_measured = True` ใช้กับค่าตรวจวัดเท่านั้น ส่วนผลพยากรณ์ทุกแถวเป็น `False`

## water_arsenic_long.csv / sediment_arsenic_long.csv / turbidity_long.csv

| คอลัมน์ | ความหมาย |
|---|---|
| obs_id | รหัสแถว `W/S/T-สถานี-รอบ-O/N` (O = ตารางทางการ, N = ข่าว) |
| media | water, sediment, turbidity |
| station_id | รหัสจุดเก็บของ คพ. เชื่อมกับ stations.csv |
| round | ครั้งที่เก็บตัวอย่าง (การนับรอบน้ำและรอบตะกอนแยกกัน) |
| sample_start, sample_end | ช่วงวันที่เก็บตัวอย่าง (ค.ศ.) |
| t_mid | วันกึ่งกลางช่วงเก็บ ใช้เป็นเวลาในแบบจำลอง |
| date_status | official, plan (วันตามแผน), news, official_conflict |
| value_reported | ข้อความตามต้นฉบับ เช่น `<0.010`, `0.011-0.014`, `เป็นไปตามมาตรฐาน` |
| value | ค่าจุด (ว่างถ้าเป็นค่าเซ็นเซอร์) |
| value_low, value_high | ขอบล่างและขอบบนของค่าจริง |
| censor | none = ค่าจุด, left = ไม่เกิน value_high, right = มากกว่า value_low, interval = อยู่ระหว่าง low และ high |
| unit | mg/L, mg/kg, NTU |
| source_type | official_table (ตาราง คพ.), news (ข่าวที่อ้าง คพ.) |
| scope | station, interval, shared_value (ข่าวให้ค่าเดียวหลายจุด), river_level (ข่าวบอกว่าทั้งลำน้ำเป็นไปตามมาตรฐาน), ambiguous |
| qc_flag | A_official > B_news_station / B_news_interval > C_news_river_level > D_ambiguous |
| needs_official_check | True เมื่อยังต้องเทียบกับตาราง คพ. |

## stations.csv
`river_group` ใช้รวมสถานีเพื่อ partial pooling (kok_main, tributary, sai, ruak, mekong)
`flows_into` และ `downstream_order` ใช้สร้างกราฟลำน้ำ (DAG)
`lat`, `lon`: พิกัด WGS84 จากรายงานตะกอนรอบ 13 ภาคผนวก ค (`geocode_status = pcd_R13_appendixC`) สถานีที่ไม่มีพิกัดให้ใช้จุดกึ่งกลางตำบลแทน
`sediment_texture_R13`: ลักษณะตะกอนที่จุดเก็บ (ทรายละเอียด, ทรายหยาบ, ทรายปนกรวด, ดินเลน, ดินร่วนปนทราย) ใช้เป็นตัวแปรร่วม เพราะตะกอนเม็ดละเอียดดูดซับสารหนูได้มากกว่า

## site_history.csv
บันทึกการย้ายจุดเก็บ `valid_from` คือวันที่เริ่มใช้จุดใหม่ ส่วน `model_station_key` คือคีย์ที่แบบจำลองใช้หลังวันที่นั้น

## sediment_metals_long.csv
1 แถวต่อ โลหะ × สถานี × รอบ มีคอลัมน์ `parameter` (As, Cd, Mn, Ni, Pb, Zn, Cu, Hg, Cr), `std_safe`, `std_severe` (mg/kg) ค่า `ND` เก็บเป็น left-censored ที่ไม่ทราบขีดจำกัด

## revisions_sediment.csv
ค่าที่ต่างกันระหว่างรายงานฉบับรอบ 12 และรอบ 13 ชุดข้อมูลใช้ค่าฉบับล่าสุดเสมอ

## model_table.csv
มี 1 แถวต่อสถานี-รอบ ถ้าสถานี-รอบเดียวกันมีทั้งตารางทางการและข่าว จะใช้ตารางทางการ คอลัมน์ที่เพิ่มมา:
`model_station_key` (คีย์สถานีที่แยกก่อน/หลังย้ายจุด), `y_low = ln(value_low)`, `y_high = ln(value_high)`, `turbidity_NTU`, `ln_turbidity`, `sin_doy`, `cos_doy`

## data/forecast/forecast_latest.json (รูปแบบ segment_forecast)
`p10, p50, p90` (mg/L), `prob_exceed` = P(C > 0.01), `is_measured = false`, `horizon_days`,
`reliability` = low เมื่อสถานีมีข้อมูลน้อยกว่า 3 ค่า หรือข้อมูลล่าสุดเก่ากว่า 120 วัน, `run_id`, `data_cutoff`

## water_metals_long.csv
1 แถวต่อ โลหะ × สถานี × รอบ (Pb, Hg, Cu, Zn, Ni, Cd) หน่วย mg/L มีคอลัมน์ `std_surface_water` (มาตรฐานน้ำผิวดิน; Cd ใช้ 0.005 สำหรับน้ำที่มีความกระด้างไม่เกิน 100 mg/L) และ `exceeds_std`
ค่าในต้นฉบับที่ควรระวังมีคำอธิบายในคอลัมน์ `note` เช่น Pb `<0.10` ในรอบ 24 ซึ่งน่าจะพิมพ์ผิดจาก `<0.010` และค่า `0.00` ที่ถูกตัดในตาราง Cd
