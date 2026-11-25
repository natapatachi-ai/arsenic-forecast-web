"""02_validate_dataset.py
ตรวจความถูกต้องของชุดข้อมูลก่อนเข้าแบบจำลอง  ถ้ามีข้อใดไม่ผ่านจะจบด้วย exit code 1
(ใช้เป็น QC gate ของกฎ "คำนวณใหม่ทุกครั้งที่ได้รับข้อมูลใหม่จากแหล่งที่ยืนยันแล้ว")

รัน:  python scripts/02_validate_dataset.py
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "processed"
errors, warns = [], []


def check(cond, msg, level="error"):
    if not cond:
        (errors if level == "error" else warns).append(msg)


st = pd.read_csv(P / "stations.csv", dtype=str)
rd = pd.read_csv(P / "rounds.csv", dtype=str)
w = pd.read_csv(P / "water_arsenic_long.csv")
t = pd.read_csv(P / "turbidity_long.csv")
s = pd.read_csv(P / "sediment_arsenic_long.csv")

# 1) โครงสร้าง
check(st.station_id.is_unique, "stations.csv มี station_id ซ้ำ")
for name, df in [("water", w), ("turbidity", t), ("sediment", s)]:
    check(df.obs_id.is_unique, f"{name}: obs_id ซ้ำ")
    unknown = set(df.station_id) - set(st.station_id)
    check(not unknown, f"{name}: station_id ไม่มีใน stations.csv -> {sorted(unknown)}")
    check(df.t_mid.notna().all(), f"{name}: มีแถวที่ไม่มีวันที่เก็บตัวอย่าง")
    check(df.source_url.notna().all(), f"{name}: มีแถวที่ไม่มีแหล่งที่มา")
    check(df.is_measured.all(), f"{name}: is_measured ต้องเป็น True ในข้อมูลตรวจวัด")
    ok_cen = df.censor.isin(["none", "left", "right", "interval"]).all()
    check(ok_cen, f"{name}: ค่า censor ไม่ถูกต้อง")
    pt = df[df.censor == "none"]
    check((pt.value_low == pt.value_high).all() and (pt.value == pt.value_low).all(),
          f"{name}: ค่าจุด (none) ต้องมี value=low=high")
    iv = df[df.censor == "interval"]
    check((iv.value_low < iv.value_high).all(), f"{name}: ช่วงค่า low ต้องน้อยกว่า high")
    s0 = pd.to_datetime(df.sample_start); s1 = pd.to_datetime(df.sample_end)
    check((s0 <= s1).all(), f"{name}: sample_start มากกว่า sample_end")

# 2) ช่วงค่าที่เป็นไปได้ทางกายภาพ
check(w.value_high.dropna().between(0.0, 5.0).all(), "water: As นอกช่วง 0-5 mg/L")
check(t.value.dropna().between(0.0, 10000).all(), "turbidity: นอกช่วง 0-10000 NTU")
check(s.value.dropna().between(0.0, 5000).all(), "sediment: As นอกช่วง 0-5000 mg/kg")
check((w[w.censor == "left"].value_high == 0.010).all(), "water: ค่า left-censored ต้องเป็นขีด 0.010")
check((s[s.censor == "left"].value_high == 5.0).all(), "sediment: ค่า left-censored ต้องเป็นขีด 5.0")

# 3) ห้ามมีค่าซ้ำจากแหล่งทางการในสถานี-รอบเดียวกัน
dup = w[w.source_type == "official_table"].duplicated(["station_id", "round"]).sum()
check(dup == 0, f"water: แถวทางการซ้ำ {dup} แถว")

# 4) ตรวจเทียบกับข้อเท็จจริงอิสระที่ตีพิมพ์ (cross-check)
r3 = w[(w["round"] == 3) & w.station_id.str.startswith("KK") & (w.value > 0.010)]
check(len(r3) == 11, f"รอบ 3: แม่น้ำกกต้องเกินมาตรฐาน 11 จุด (ข่าว คพ.) แต่ได้ {len(r3)}")
check(np.isclose(w.query("station_id=='SA02' and `round`==8").value.iloc[0], 0.053), "SA02 R8 ต้องเป็น 0.053")
check(np.isclose(s.query("station_id=='KK01' and `round`==1").value.iloc[0], 33), "ตะกอน KK01 R1 ต้องเป็น 33")
check(np.isclose(s.query("station_id=='NK01' and `round`==10").value.iloc[0], 296), "ตะกอน NK01 R10 ต้องเป็น 296")
check(np.isclose(w.query("station_id=='SA01' and `round`==22").value.iloc[0], 0.284), "SA01 R22 ต้องเป็น 0.284")
r11 = w[(w["round"] == 11) & (w.censor == "none")]
check(np.isclose(r11.value.max(), 0.026), "รอบ 11: ค่าสูงสุดต้องเป็น 0.026 ตามข่าว คพ.")
check(np.isclose(w.query("station_id=='RU01' and `round`==22").value.iloc[0], 0.017), "RU01 R22 ต้องเป็น 0.017 (ตาราง คพ.)")
check(len(w[w.source_type=="official_table"]["round"].unique()) == 24, "ข้อมูลน้ำทางการต้องครบ 24 รอบ")

# 5) คำเตือน (ไม่หยุดการทำงาน)
lat = pd.to_numeric(st.lat, errors="coerce"); lon = pd.to_numeric(st.lon, errors="coerce")
BOX = {"kok_basin": (19.0, 21.0, 99.0, 101.0), "salween": (17.5, 19.5, 97.3, 98.4), "mekong_ne": (16.5, 18.6, 101.3, 105.0)}
net = st["network"].fillna("kok_basin") if "network" in st else pd.Series("kok_basin", index=st.index)
inside = [pd.isna(a) or pd.isna(o) or (BOX[n][0] <= a <= BOX[n][1] and BOX[n][2] <= o <= BOX[n][3]) for a, o, n in zip(lat, lon, net)]
check(all(inside), "พิกัดสถานีอยู่นอกกรอบพื้นที่ของเครือข่าย (กก-โขงเหนือ / สาละวิน / โขงอีสาน)")
nocoord = st.loc[lat.isna(), "station_id"].tolist()
check(not nocoord, f"สถานีที่ยังไม่มีพิกัด: {nocoord}", "warn")
check(np.isclose(s.query("station_id=='RU02' and `round`==13").value.iloc[0], 107), "ตะกอน RU02 R13 ต้องเป็น 107")
check(np.isclose(s.query("station_id=='KK05' and `round`==12").value.iloc[0], 11), "ตะกอน KK05 R12 ต้องเป็น 11 (ฉบับแก้)")
mt = pd.read_csv(P / "sediment_metals_long.csv")
check(len(mt[mt.parameter == "As"]) == len(s), "จำนวนค่า As ในตารางโลหะต้องเท่ากับตาราง As")
check(mt.parameter.nunique() == 9, "ตารางโลหะต้องมี 9 พารามิเตอร์")
wm = pd.read_csv(P / "water_metals_long.csv")
check(set(wm.parameter) == {"Pb", "Hg", "Cu", "Zn", "Ni", "Cd"}, "ตารางโลหะในน้ำต้องมี Pb Hg Cu Zn Ni Cd")
check(np.isclose(wm.query("parameter=='Pb' and station_id=='SA01' and `round`==22").value.iloc[0], 0.266), "Pb SA01 R22 ต้องเป็น 0.266")
check(wm.t_mid.notna().all(), "ตารางโลหะในน้ำต้องมีวันที่ครบ")
all_r = set(rd[rd.media == "water"]["round"].astype(int))
miss = sorted(all_r - set(w["round"]))
check(not miss, f"ยังไม่มีค่าสารหนูในน้ำรอบ {miss}", "warn")
news_share = (w.source_type == "news").mean()
check(news_share < 0.2, f"ข้อมูลน้ำมาจากข่าว {news_share:.0%} ควรแทนด้วยตาราง คพ. เมื่อได้มา", "warn")

print(f"rows: water={len(w)} turbidity={len(t)} sediment={len(s)} stations={len(st)}")
for m in warns:
    print("WARN :", m)
for m in errors:
    print("ERROR:", m)
print("ผลตรวจ:", "ผ่าน" if not errors else f"ไม่ผ่าน {len(errors)} ข้อ")
sys.exit(1 if errors else 0)
