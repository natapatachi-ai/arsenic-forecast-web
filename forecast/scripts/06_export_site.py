"""06_export_site.py  ส่งออกข้อมูลที่หน้าเว็บใช้ไปไว้ที่ ../web/data/
- forecast_latest.json   ผลพยากรณ์ (is_measured = false)
- observations.json      ข้อมูลจุดตรวจทุกเครือข่าย พร้อมพิกัด ตำบล อำเภอ จังหวัด และค่าล่าสุด (is_measured = true)
- history.json           ค่าตรวจวัดทุกรอบของทุกจุด (is_measured = true)
- backtest.json          ค่าพยากรณ์ย้อนหลัง 1 รอบล่วงหน้า เทียบกับค่าที่ตรวจวัดจริง (is_measured = false สำหรับค่าพยากรณ์)
- context.json           จังหวัด/ตำบลที่ได้รับผลกระทบ มาตรการบำบัดและผล ลำดับการไหลของแม่น้ำ (พร้อมแหล่งที่มา)
- meta.json              run_id, เวลาที่คำนวณ, ข้อมูลล่าสุดของแต่ละเครือข่าย, ผลทดสอบย้อนหลัง
หน้าเว็บอ่านไฟล์เหล่านี้ทุกครั้งที่เปิด จึงแสดงผลล่าสุดทันทีหลัง deploy
"""
from pathlib import Path
import json
import shutil
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "processed"
F = ROOT / "data" / "forecast"
C = ROOT / "data" / "context"
OUT = ROOT.parent / "web" / "data"   # โฟลเดอร์เว็บอยู่ข้าง forecast/
NETWORK_TH = {"kok_basin": "ลุ่มน้ำกก–สาย–รวก–โขง (เชียงใหม่ เชียงราย)", "salween": "แม่น้ำสาละวินและลำน้ำสาขา (แม่ฮ่องสอน)",
              "mekong_ne": "แม่น้ำโขงภาคตะวันออกเฉียงเหนือ (เลย หนองคาย บึงกาฬ นครพนม)"}
NETWORK_SRC = {"kok_basin": "คพ./สคพ.1 รายงานแม่น้ำกก–สาย–รวก–โขง ครั้งที่ 1–24",
               "salween": "คพ./สคพ.1 รายงานแม่น้ำสาละวินและลำน้ำสาขา ครั้งที่ 1–8",
               "mekong_ne": "สคพ.9 อุดรธานี รายงานคุณภาพน้ำแหล่งน้ำผิวดิน ปีงบประมาณ 2569 ครั้งที่ 1–4"}


def nz(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else v


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copy(F / "forecast_latest.json", OUT / "forecast_latest.json")
    st = pd.read_csv(P / "stations.csv", dtype=str).fillna("")
    w = pd.read_csv(P / "water_arsenic_long.csv")
    w["network"] = w["network"].fillna("kok_basin")
    last = w.sort_values("t_mid").groupby("station_id").tail(1).set_index("station_id")
    obs = []
    for _, s in st.iterrows():
        if s.station_id not in last.index:
            continue
        r = last.loc[s.station_id]
        lat = s.water_lat or s.lat
        lon = s.water_lon or s.lon
        obs.append(dict(station_id=s.station_id, network=s.network or "kok_basin", river=s.river_th, site=s.site_name_th,
                        tambon=s.tambon_th, amphoe=s.amphoe_th, province=s.province_th,
                        lat=float(lat) if lat else None, lon=float(lon) if lon else None,
                        geocode_status=s.geocode_status, note=s.note, flows_into=s.flows_into,
                        round=int(r["round"]), sample_end=r.sample_end, t_mid=r.t_mid, value_reported=str(r.value_reported),
                        censor=r.censor, unit="mg/L", is_measured=True, source=r.source_url))
    (OUT / "observations.json").write_text(json.dumps(obs, ensure_ascii=False, indent=1), encoding="utf-8")

    turb = pd.read_csv(P / "turbidity_long.csv")[["station_id", "round", "value"]].rename(columns={"value": "turbidity_NTU"})
    h = w.merge(turb, on=["station_id", "round"], how="left").sort_values(["station_id", "t_mid"])
    hist = {}
    for sid, g in h.groupby("station_id"):
        hist[sid] = [dict(round=int(r["round"]), network=r.network, t_mid=r.t_mid, sample_start=r.sample_start, sample_end=r.sample_end,
                          date_status=r.date_status, value_reported=str(r.value_reported), value=nz(r.value),
                          value_low=nz(r.value_low), value_high=nz(r.value_high), censor=r.censor,
                          turbidity_NTU=nz(r.turbidity_NTU), is_measured=True) for _, r in g.iterrows()]
    (OUT / "history.json").write_text(json.dumps(hist, ensure_ascii=False), encoding="utf-8")

    fc = json.loads((F / "forecast_latest.json").read_text(encoding="utf-8"))
    k = fc["model"]["interval_calibration_k"]
    # ค่าพยากรณ์ย้อนหลัง: แต่ละรอบใช้เฉพาะข้อมูลก่อนวันเก็บตัวอย่างรอบนั้น
    v = pd.read_csv(F / "validation_rolling.csv")
    z = stats.norm.ppf(0.9)
    bt = {}
    for _, r in v.iterrows():
        sid = str(r.station_id_pcd)
        m, s = r.pred_ln_mean, r.pred_ln_sd * k
        bt.setdefault(sid, []).append(dict(t=r.t_target, round=int(r.origin_round), network=r.network, horizon_days=int(r.horizon_days),
                                           p10=float(np.exp(m - z * s)), p50=float(np.exp(m)), p90=float(np.exp(m + z * s)),
                                           prob_exceed=float(stats.norm.sf((np.log(0.01) - m) / s)),
                                           obs_reported=str(r.value_reported), obs_censor=r.censor,
                                           obs_value=None if r.censor != "none" else float(np.exp(r.obs_ln)),
                                           in_band=None if r.censor != "none" else bool(m - z * s <= r.obs_ln <= m + z * s),
                                           is_measured=False))
    (OUT / "backtest.json").write_text(json.dumps(bt, ensure_ascii=False), encoding="utf-8")

    ctx = {n: json.loads((C / f"{n}.json").read_text(encoding="utf-8")) for n in ("affected_areas", "treatment_measures", "river_flow")}
    (OUT / "context.json").write_text(json.dumps(ctx, ensure_ascii=False), encoding="utf-8")

    vs = json.loads((F / "validation_summary.json").read_text(encoding="utf-8"))
    beta = json.loads((F / "model_A_turbidity.json").read_text(encoding="utf-8"))
    nets = {}
    for nw, g in w.groupby("network"):
        lr = g[g["round"] == g["round"].max()]
        nets[nw] = dict(name_th=NETWORK_TH.get(nw, nw), source=NETWORK_SRC.get(nw, ""), latest_round=int(g["round"].max()),
                        latest_start=str(lr.sample_start.min()), latest_end=str(lr.sample_end.max()),
                        n_stations=int(g.station_id.nunique()), target_date=fc.get("target_date_by_network", {}).get(nw, fc["target_date"]))
    meta = dict(run_id=fc["run_id"], generated_at=fc["generated_at"], data_cutoff=fc["data_cutoff"],
                latest_water_round=int(w[w.network == "kok_basin"]["round"].max()), networks=nets,
                validation=vs, model_A=dict(beta=beta["beta_ln_turbidity"], ci95=beta["ci95"], n_obs=beta["n_obs"]),
                interval_k=k, disclaimer=fc["disclaimer"])
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print("exported", len(obs), "stations,", sum(len(x) for x in bt.values()), "backtest pairs ->", OUT)


if __name__ == "__main__":
    main()
