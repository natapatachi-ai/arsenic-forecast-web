"""01_build_dataset.py
แปลงตารางที่ถอดจากรายงาน คพ. และข่าว (data/raw_tables) ให้เป็นตารางยาว (long format)
พร้อมใช้กับแบบจำลองที่รองรับข้อมูลถูกเซ็นเซอร์ (censored / interval data)

ผลลัพธ์ใน data/processed/
  water_arsenic_long.csv     สารหนูในน้ำผิวดิน (mg/L)
  turbidity_long.csv         ความขุ่น (NTU)
  sediment_arsenic_long.csv  สารหนูในตะกอนดิน (mg/kg)
  model_table.csv            ตารางรวมสำหรับแบบจำลอง (น้ำ + ความขุ่น + เวลา)

รัน:  python scripts/01_build_dataset.py
"""
from pathlib import Path
import hashlib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw_tables"
OUT = ROOT / "data" / "processed"

SRC_WATER_R1_10 = "https://www.pcd.go.th/wp-content/uploads/2025/09/pcdnew-2025-09-15_08-53-08_171613.pdf"
SRC_WATER_R1_24 = ("คพ. รายงานผลคุณภาพน้ำผิวดิน แม่น้ำกก-สาย-รวก-โขง ครั้งที่ 24 (ข้อมูล ณ 18 พ.ย. 2569) ภาคผนวก ข "
                   "https://epo01.pcd.go.th/th/information/more/358")
SRC_SED_R1_13 = ("คพ. สถานการณ์คุณภาพตะกอนดินฯ ครั้งที่ 13 (ข้อมูล ณ 15 ต.ค. 2569) ภาคผนวก ข "
                 "https://epo01.pcd.go.th/th/information/more/358")
SED_STD = {"As": (10, 33), "Cd": (1, 5), "Ni": (23, 50), "Pb": (36, 130), "Zn": (120, 460),
           "Cu": (31.5, 150), "Hg": (0.2, 1.0), "Cr": (43.4, 110), "Mn": (None, None)}


def latest(pattern):
    """ไฟล์ล่าสุดตามเลขรอบในชื่อไฟล์ เช่น water_as_R01-R25_pcd.csv"""
    import re
    files = sorted(RAW.glob(pattern), key=lambda p: int(re.search(r"R(\d+)_pcd", p.name).group(1)))
    if not files:
        raise FileNotFoundError(pattern)
    return files[-1]


def parse_cell(raw: str):
    """คืนค่า (value_point, low, high, censor) จากข้อความในตาราง คพ."""
    s = str(raw).strip()
    if s in {"-", "", "nan"}:
        return None
    if s.startswith("<") or s.startswith("≤"):
        # "<0.010" = ต่ำกว่าขีดจำกัดการตรวจวัด; "≤0.010" (สคพ.9) = ไม่เกินค่ามาตรฐาน -> ทั้งคู่เป็น left-censored ที่ขีดนั้น
        lim = float(s[1:])
        return (np.nan, np.nan, lim, "left")
    v = float(s.replace(",", ""))
    return (v, v, v, "none")


def wide_to_long(path, media, unit, source_url, source_type="official_table"):
    df = pd.read_csv(path, dtype=str)
    rows = []
    for _, r in df.iterrows():
        for col in df.columns[1:]:
            parsed = parse_cell(r[col])
            if parsed is None:
                continue  # ไม่ได้เก็บตัวอย่าง
            v, lo, hi, cen = parsed
            rows.append(dict(media=media, station_id=r["station_id"], round=int(col[1:]),
                             value_reported=r[col], value=v, value_low=lo, value_high=hi,
                             censor=cen, unit=unit, source_type=source_type, scope="station",
                             source_url=source_url, note=""))
    return pd.DataFrame(rows)


def news_to_long(path, media, unit):
    df = pd.read_csv(path, dtype={"value_reported": str, "note": str})
    out = []
    for _, r in df.iterrows():
        lo = r["value_low"] if pd.notna(r["value_low"]) else np.nan
        hi = r["value_high"] if pd.notna(r["value_high"]) else np.nan
        if pd.notna(lo) and pd.notna(hi) and lo == hi:
            cen, v = "none", lo
        elif pd.isna(lo) and pd.notna(hi):
            cen, v = "left", np.nan
        elif pd.notna(lo) and pd.isna(hi):
            cen, v = "right", np.nan
        else:
            cen, v = "interval", np.nan
        out.append(dict(media=media, station_id=r["station_id"], round=int(r["round"]),
                        value_reported=r["value_reported"], value=v, value_low=lo, value_high=hi,
                        censor=cen, unit=unit, source_type="news", scope=r["scope"],
                        source_url=r["source_url"], note=r["note"] if pd.notna(r["note"]) else ""))
    return pd.DataFrame(out)


def attach_dates(df, rounds, media):
    rr = rounds[rounds["media"] == media][["round", "sample_start", "sample_end", "date_status"]]
    df = df.merge(rr, on="round", how="left")
    s = pd.to_datetime(df["sample_start"])
    e = pd.to_datetime(df["sample_end"])
    df["t_mid"] = (s + (e - s) / 2).dt.date.astype(str)
    df.loc[s.isna(), "t_mid"] = ""
    return df


NETWORKS = {
    # เครือข่ายเฝ้าระวังอื่นนอกลุ่มน้ำกก (เลขรอบนับแยกตามเครือข่าย)
    "salween": dict(water="networks/salween_water_as_R01-R*_epo01.csv", turb="networks/salween_turbidity_R01-R*_epo01.csv",
                    rounds="networks/salween_rounds.csv"),
    "mekong_ne": dict(water="networks/mekong_ne_water_as_R01-R*_epo09.csv", turb="networks/mekong_ne_turbidity_R01-R*_epo09.csv",
                      rounds="networks/mekong_ne_rounds.csv"),
}


def latest_any(pattern):
    import re
    files = sorted(RAW.glob(pattern), key=lambda p: int(re.search(r"R01-R(\d+)", p.name).group(1)))
    return files[-1] if files else None


def build_network(net, cfg):
    rr = pd.read_csv(RAW / cfg["rounds"], dtype=str)
    rr["round"] = rr["round"].astype(int)
    src = rr.source_url.iloc[-1]
    out = {}
    for key, media, unit, pref in (("water", "water", "mg/L", "W"), ("turb", "water", "NTU", "T")):
        f = latest_any(cfg[key])
        if f is None:
            continue
        d = wide_to_long(f, media, unit, "")
        d = attach_dates(d, rr, "water")
        d["source_url"] = d["round"].map(dict(zip(rr["round"], rr.source_url))).fillna(src)
        d = finalize(d, f"{pref}-{net}")
        d["network"] = net
        if key == "turb":
            d["media"] = "turbidity"
        out[key] = d
    return out


def finalize(df, prefix):
    df = df.sort_values(["station_id", "round", "source_type"]).reset_index(drop=True)
    # qc_flag: ระดับความน่าเชื่อถือที่แบบจำลองใช้กรอง
    def qc(r):
        if r["source_type"] == "official_table":
            return "A_official"
        if r["scope"] in ("station", "shared_value"):
            return "B_news_station"
        if r["scope"] == "interval":
            return "B_news_interval"
        if r["scope"] == "river_level":
            return "C_news_river_level"
        return "D_ambiguous"
    df["qc_flag"] = df.apply(qc, axis=1)
    df["is_measured"] = True
    df["needs_official_check"] = df["source_type"] != "official_table"
    df.insert(0, "obs_id", [f"{prefix}-{r.station_id}-R{r['round']:02d}-{'O' if r.source_type=='official_table' else 'N'}"
                            for _, r in df.iterrows()])
    cols = ["obs_id", "media", "station_id", "round", "sample_start", "sample_end", "t_mid", "date_status",
            "value_reported", "value", "value_low", "value_high", "censor", "unit", "is_measured",
            "source_type", "scope", "qc_flag", "needs_official_check", "source_url", "note"]
    return df[cols]


def main():
    rounds = pd.read_csv(OUT / "rounds.csv", dtype=str)
    rounds["round"] = rounds["round"].astype(int)

    w_off = wide_to_long(latest("water_as_R01-R*_pcd.csv"), "water", "mg/L", SRC_WATER_R1_24)
    news_files = sorted(RAW.glob("water_as_news_*.csv"))  # ใช้เมื่อมีรอบใหม่ที่ยังไม่มีตาราง คพ.
    w_news = pd.concat([news_to_long(f, "water", "mg/L") for f in news_files]) if news_files else pd.DataFrame()
    if len(w_news):
        w_news = w_news.merge(w_off[["station_id", "round"]], on=["station_id", "round"], how="left", indicator=True)
        w_news = w_news[w_news._merge == "left_only"].drop(columns="_merge")
    water = finalize(attach_dates(pd.concat([w_off, w_news]), rounds, "water"), "W")
    # หมายเหตุเฉพาะจุดที่ตรวจพบความไม่สอดคล้องในรายงาน
    water.loc[(water.station_id == "RU01") & (water["round"] == 22), "note"] = "ข่าวรายงาน 0.17 แต่ตาราง คพ. เป็น 0.017"
    water.loc[(water.station_id == "RU02") & (water["round"] == 22), "note"] = "ข่าวรายงาน 0.12 แต่ตาราง คพ. เป็น 0.012"

    t1 = wide_to_long(RAW / "turbidity_R01-R10_pcd.csv", "water", "NTU", SRC_WATER_R1_10)
    t2 = wide_to_long(latest("turbidity_R11-R*_pcd.csv"), "water", "NTU", SRC_WATER_R1_24)
    turb = finalize(attach_dates(pd.concat([t1, t2]), rounds, "water"), "T")
    turb.loc[(turb.station_id == "KK07") & (turb["round"] == 22), "note"] = "ช่องว่างในตารางต้นฉบับ"
    turb["media"] = "turbidity"
    water["network"] = "kok_basin"; turb["network"] = "kok_basin"
    for net, cfg in NETWORKS.items():
        b = build_network(net, cfg)
        water = pd.concat([water, b["water"]], ignore_index=True)
        if "turb" in b:
            turb = pd.concat([turb, b["turb"]], ignore_index=True)

    s_off = wide_to_long(latest("sediment_as_R01-R*_pcd.csv"), "sediment", "mg/kg", SRC_SED_R1_13)
    s_off.loc[(s_off.station_id == "KK05") & (s_off["round"] == 12), "note"] = \
        "รายงานรอบ 12 ระบุ 29 รายงานรอบ 13 แก้เป็น 11 (ใช้ค่าล่าสุด)"
    sed = finalize(attach_dates(s_off, rounds, "sediment"), "S")

    # โลหะหนักอื่นในตะกอน (ใช้เป็นตัวแปรร่วมทางเคมี เช่น Mn ซึ่งสัมพันธ์กับออกไซด์ที่ดูดซับสารหนู)
    mt = pd.read_csv(latest("sediment_metals_R01-R*_pcd.csv"), dtype=str)
    mrows = []
    for _, r in mt.iterrows():
        raw = r.value_reported
        if raw == "-":
            continue
        if raw == "ND":
            v, lo, hi, cen = np.nan, np.nan, np.nan, "left"
        else:
            v, lo, hi, cen = parse_cell(raw)
        safe, harm = SED_STD[r.parameter_en]
        mrows.append(dict(media="sediment", parameter=r.parameter_en, parameter_th=r.parameter,
                          station_id=r.station_id, round=int(r["round"]), value_reported=raw, value=v,
                          value_low=lo, value_high=hi, censor=cen, unit="mg/kg",
                          std_safe=safe, std_severe=harm, source_type="official_table", source_url=SRC_SED_R1_13))
    metals = attach_dates(pd.DataFrame(mrows), rounds, "sediment")
    metals["is_measured"] = True
    metals.to_csv(OUT / "sediment_metals_long.csv", index=False)

    # โลหะหนักอื่นในน้ำผิวดิน รอบ 1-24 (Pb, Hg, Cu, Zn, Ni, Cd)
    WSTD = {"Pb": 0.05, "Hg": 0.002, "Cu": 0.1, "Zn": 1.0, "Ni": 0.1, "Cd": 0.005, "As": 0.01}
    wrows, param = [], None
    for line in latest("water_metals_R01-R*_pcd.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("#") and line[1:3] in WSTD:
            param = line[1:3]; continue
        if not line or line.startswith("#"):
            continue
        cells = line.split(";")
        if cells[0] == "station":
            hdr = [int(c[1:]) for c in cells[1:]]; continue
        for rnd, raw in zip(hdr, cells[1:]):
            raw = raw.strip()
            if raw in ("", "-"):
                continue
            v, lo, hi, cen = parse_cell(raw)
            note = ""
            if param == "Pb" and raw == "<0.10":
                note = "ขีดจำกัด <0.10 ในต้นฉบับ อาจพิมพ์ผิดจาก <0.010"
            if raw == "0.00":
                note = "ค่าถูกตัดในต้นฉบับ (แสดง 0.00)"
            wrows.append(dict(media="water", parameter=param, station_id=cells[0], round=rnd, value_reported=raw,
                              value=v, value_low=lo, value_high=hi, censor=cen, unit="mg/L", std_surface_water=WSTD[param],
                              source_type="official_table", source_url=SRC_WATER_R1_24, note=note))
    wmet = attach_dates(pd.DataFrame(wrows), rounds, "water")
    wmet["is_measured"] = True
    wmet["exceeds_std"] = wmet["value"] > wmet["std_surface_water"]
    wmet.to_csv(OUT / "water_metals_long.csv", index=False)

    water.to_csv(OUT / "water_arsenic_long.csv", index=False)
    turb.to_csv(OUT / "turbidity_long.csv", index=False)
    sed.to_csv(OUT / "sediment_arsenic_long.csv", index=False)

    # ตารางสำหรับแบบจำลอง: 1 แถวต่อ สถานี-รอบ (ใช้แหล่งทางการก่อนข่าว)
    m = water.sort_values("qc_flag").drop_duplicates(["station_id", "round"], keep="first")
    tb = turb[["station_id", "round", "value"]].rename(columns={"value": "turbidity_NTU"})
    m = m.merge(tb, on=["station_id", "round"], how="left")
    st = pd.read_csv(OUT / "stations.csv", dtype=str)[["station_id", "river_en", "river_group",
                                                         "downstream_order", "province_th", "amphoe_th", "tambon_th"]]
    m = m.drop(columns=[c for c in ("network",) if c in m.columns]).merge(
        water[["obs_id", "network"]], on="obs_id", how="left")
    m = m.merge(st, on="station_id", how="left")
    m["y_low"] = np.log(m["value_low"])
    m["y_high"] = np.log(m["value_high"])
    m["ln_turbidity"] = np.log(m["turbidity_NTU"])
    t = pd.to_datetime(m["t_mid"], errors="coerce")
    doy = t.dt.dayofyear
    m["sin_doy"] = np.sin(2 * np.pi * doy / 365.25)
    m["cos_doy"] = np.cos(2 * np.pi * doy / 365.25)
    # สถานีที่ย้ายตำแหน่ง ให้แยกเป็นคีย์ใหม่ในแบบจำลอง (structural break)
    m["model_station_key"] = m["station_id"]
    sh = pd.read_csv(OUT / "site_history.csv", dtype=str)
    for _, h in sh.iterrows():
        moved = (m.station_id == h.station_id) & (t >= pd.Timestamp(h.valid_from))
        m.loc[moved, "model_station_key"] = h.model_station_key
    m = m.sort_values(["station_id", "round"]).reset_index(drop=True)
    m.to_csv(OUT / "model_table.csv", index=False)

    # บันทึก hash สำหรับตรวจว่าข้อมูลเปลี่ยนหรือไม่ (ใช้กับกฎคำนวณใหม่เมื่อมีข้อมูลใหม่)
    with open(OUT / "MANIFEST.sha256", "w", encoding="utf-8") as f:
        for p in sorted(list(RAW.glob("*.csv")) + list(RAW.glob("networks/*.csv")) + list(OUT.glob("*.csv"))):
            f.write(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ROOT)}\n")

    print(f"water obs: {len(water)} (official {sum(water.source_type=='official_table')}, news {sum(water.source_type=='news')})")
    print(f"turbidity obs: {len(turb)}  sediment As obs: {len(sed)}  sediment metals obs: {len(metals)}  water metals obs: {len(wmet)}  model rows: {len(m)}")


if __name__ == "__main__":
    main()
