"""03_forecast_baseline.py
แบบจำลองพื้นฐาน (baseline) สำหรับพยากรณ์สารหนูในน้ำผิวดินรายสถานี จากข้อมูลที่ถูกเซ็นเซอร์

แบบจำลอง B (ใช้พยากรณ์): Censored log-AR(1) แบบช่วงเวลาไม่สม่ำเสมอ (Ornstein-Uhlenbeck แบบไม่ต่อเนื่อง)
    y = ln C
    y_t | y_prev ~ Normal( a_s + rho^d (y_prev - a_s),  sigma^2 (1 - rho^(2d)) ),   d = Δt / 14 วัน
    a_s ~ ถูกดึงเข้าหาค่ากลางของกลุ่มลำน้ำ mu_g ด้วย ridge penalty  lambda (a_s - mu_g)^2
    ค่าที่รายงานเป็น "<0.010" ใช้ likelihood แบบ Tobit:  P(y <= ln 0.010)
    ค่าช่วง (เช่น 0.011-0.014) ใช้ P(ln lo < y <= ln hi)
    ค่า y_prev ที่ถูกเซ็นเซอร์ แทนด้วยค่าคาดหมายของ truncated normal และวนปรับ 6 รอบ (EM แบบประมาณ)

แบบจำลอง A (อธิบาย, รอบ 1-10): Tobit  y = a_s + beta * ln(turbidity) + e
    ใช้ทดสอบสมมติฐานทางเคมีว่าสารหนูส่วนใหญ่เกาะอนุภาค (Kd*TSS) -> beta > 0

ผลลัพธ์ใน data/forecast/
    forecast_latest.json / .csv   P10, P50, P90 และ P(C > 0.01) ทุกสถานี  (is_measured = false)
    validation_rolling.csv        ผลทดสอบแบบ rolling origin เทียบกับ persistence
    model_A_turbidity.json        สัมประสิทธิ์ beta และช่วงความเชื่อมั่น

รัน:  python scripts/03_forecast_baseline.py [--qc A,B] [--target-date 2026-12-10]
"""
from pathlib import Path
import argparse
import json
import datetime as dt
import numpy as np
import pandas as pd
from scipy import optimize, stats

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "processed"
OUT = ROOT / "data" / "forecast"
PAR = json.loads((ROOT / "config" / "parameters.json").read_text(encoding="utf-8"))["model"]
THR = PAR["exceedance_threshold_mgL"]
LAM = PAR["ridge_lambda_station"]
STEP = PAR["reference_interval_days"]
NORM = stats.norm


# ---------- ข้อมูล ----------
def load(qc_levels):
    m = pd.read_csv(P / "model_table.csv")
    m = m[m.qc_flag.str[0].isin(qc_levels)].copy()
    m["station_id_pcd"] = m["station_id"]
    m["station_id"] = m["model_station_key"]  # แยกช่วงก่อน/หลังย้ายจุดเก็บ
    m["t"] = pd.to_datetime(m.t_mid)
    if "network" not in m: m["network"] = "kok_basin"
    m["network"] = m["network"].fillna("kok_basin")
    m = m.sort_values(["station_id", "t"]).reset_index(drop=True)
    m["lo"] = np.log(m.value_low)   # NaN = ไม่มีขอบล่าง
    m["hi"] = np.log(m.value_high)  # NaN = ไม่มีขอบบน
    return m


def init_impute(m):
    y = np.where(m.censor == "none", m.lo,
         np.where(m.censor == "left", m.hi - 0.35,
          np.where(m.censor == "right", m.lo + 0.2, (m.lo + m.hi) / 2)))
    return y


def truncnorm_mean(mu, sd, lo, hi):
    a = np.where(np.isnan(lo), -np.inf, (lo - mu) / sd)
    b = np.where(np.isnan(hi), np.inf, (hi - mu) / sd)
    Z = np.clip(NORM.cdf(b) - NORM.cdf(a), 1e-12, None)
    return mu + sd * (NORM.pdf(a) - NORM.pdf(b)) / Z


# ---------- แบบจำลอง B ----------
class CensoredAR1:
    def __init__(self, df):
        self.df = df.reset_index(drop=True)
        self.st = sorted(df.station_id.unique())
        self.gr = sorted(df.river_group.fillna("other").unique())
        self.si = self.df.station_id.map({s: i for i, s in enumerate(self.st)}).to_numpy()
        g_of_s = (self.df.drop_duplicates("station_id").set_index("station_id").river_group
                  .fillna("other").reindex(self.st))
        self.gi_s = g_of_s.map({g: i for i, g in enumerate(self.gr)}).to_numpy()
        prev_same = self.df.station_id.eq(self.df.station_id.shift())
        self.first = ~prev_same.to_numpy()
        dd = (self.df.t - self.df.t.shift()).dt.days.to_numpy() / STEP
        self.d = np.where(self.first, 1.0, dd)
        self.cen = self.df.censor.to_numpy()
        self.lo = self.df.lo.to_numpy(); self.hi = self.df.hi.to_numpy()
        self.y_imp = init_impute(self.df)

    def unpack(self, th):
        nS, nG = len(self.st), len(self.gr)
        a = th[:nS]; mu = th[nS:nS + nG]
        rho = 1 / (1 + np.exp(-th[nS + nG])); sig = np.exp(th[nS + nG + 1])
        return a, mu, rho, sig

    def moments(self, th):
        a, mu, rho, sig = self.unpack(th)
        a_i = a[self.si]
        yprev = np.r_[np.nan, self.y_imp[:-1]]
        rd = rho ** self.d
        mean = np.where(self.first, a_i, a_i + rd * (yprev - a_i))
        sd = np.where(self.first, sig, sig * np.sqrt(np.clip(1 - rd ** 2, 1e-6, None)))
        return mean, sd

    def nll(self, th):
        a, mu, rho, sig = self.unpack(th)
        mean, sd = self.moments(th)
        ll = np.zeros(len(mean))
        c = self.cen
        k = c == "none"; ll[k] = NORM.logpdf(self.lo[k], mean[k], sd[k])
        k = c == "left"; ll[k] = NORM.logcdf((self.hi[k] - mean[k]) / sd[k])
        k = c == "right"; ll[k] = NORM.logsf((self.lo[k] - mean[k]) / sd[k])
        k = c == "interval"
        ll[k] = np.log(np.clip(NORM.cdf((self.hi[k] - mean[k]) / sd[k]) - NORM.cdf((self.lo[k] - mean[k]) / sd[k]), 1e-12, None))
        pen = LAM * np.sum((a - mu[self.gi_s]) ** 2) + 0.01 * np.sum((mu - np.log(THR)) ** 2)
        return -ll.sum() + pen

    def fit(self, n_em=6):
        nS, nG = len(self.st), len(self.gr)
        th = np.r_[np.full(nS, np.log(0.012)), np.full(nG, np.log(0.012)), 0.5, np.log(0.5)]
        for _ in range(n_em):
            res = optimize.minimize(self.nll, th, method="L-BFGS-B")
            th = res.x
            mean, sd = self.moments(th)
            imp = truncnorm_mean(mean, sd, self.lo, self.hi)
            self.y_imp = np.where(self.cen == "none", self.lo, imp)
        self.th, self.res = th, res
        return self

    def predict(self, station, t_target):
        a, mu, rho, sig = self.unpack(self.th)
        if station in self.st:
            i = self.st.index(station)
            rows = np.where(self.si == i)[0]
            j = rows[-1]
            d = max((t_target - self.df.t.iloc[j]).days / STEP, 1e-3)
            rd = rho ** d
            m = a[i] + rd * (self.y_imp[j] - a[i])
            s = sig * np.sqrt(1 - rd ** 2)
            return m, s, self.df.t.iloc[j]
        return None


def summarize(m, s):
    q = {f"p{int(p*100)}": float(np.exp(m + s * NORM.ppf(p))) for p in PAR["quantiles"]}
    q["prob_exceed"] = float(NORM.sf((np.log(THR) - m) / s))
    return q


# ---------- แบบจำลอง A ----------
def fit_model_A(df):
    d = df[df.ln_turbidity.notna() & (df.source_type == "official_table")].reset_index(drop=True)
    st = sorted(d.station_id.unique()); si = d.station_id.map({s: i for i, s in enumerate(st)}).to_numpy()
    x = d.ln_turbidity.to_numpy() - d.ln_turbidity.mean()
    cen = d.censor.to_numpy(); lo = d.lo.to_numpy(); hi = d.hi.to_numpy()

    def nll(th):
        a = th[:len(st)]; b = th[-2]; sig = np.exp(th[-1])
        mu = a[si] + b * x
        ll = np.where(cen == "none", NORM.logpdf(lo, mu, sig), NORM.logcdf((hi - mu) / sig))
        return -ll.sum() + LAM * np.sum((a - a.mean()) ** 2)
    th0 = np.r_[np.full(len(st), np.log(0.012)), 0.0, np.log(0.4)]
    r = optimize.minimize(nll, th0, method="BFGS")
    se = np.sqrt(np.diag(r.hess_inv))
    return {"beta_ln_turbidity": float(r.x[-2]), "se": float(se[-2]),
            "ci95": [float(r.x[-2] - 1.96 * se[-2]), float(r.x[-2] + 1.96 * se[-2])],
            "sigma_log": float(np.exp(r.x[-1])), "n_obs": int(len(d)), "n_stations": len(st),
            "interpretation": "beta คือการเปลี่ยนแปลงของ ln C เมื่อ ln(ความขุ่น) เพิ่ม 1 หน่วย; ถ้า > 0 สอดคล้องกับสารหนูเกาะอนุภาค (Kd*TSS)"}


# ---------- การทดสอบย้อนหลัง ----------
def outcome_exceed(r):
    if r.censor == "none": return float(np.exp(r.lo) > THR)
    if r.censor == "left" and r.value_high <= THR: return 0.0
    if r.censor in ("right", "interval") and r.value_low >= THR: return 1.0
    return np.nan


def rolling_validation(df, start_round):
    """ทดสอบย้อนหลังแบบ rolling origin ตามเวลา: ทุกเครือข่ายและทุกรอบ ฝึกด้วยข้อมูลที่เก็บก่อนวันเริ่มเก็บรอบนั้นเท่านั้น
    (ไม่มีข้อมูลอนาคตรั่วข้ามเครือข่าย) แล้วพยากรณ์ 1 รอบล่วงหน้าเทียบกับค่าที่ คพ. ตรวจวัดจริง"""
    out = []
    net = df["network"] if "network" in df else pd.Series("kok_basin", index=df.index)
    first_round = {"kok_basin": start_round}
    for (nw, k), test in df.groupby([net, "round"]):
        if k < first_round.get(nw, 2): continue
        t0 = pd.to_datetime(test.sample_start).min() if "sample_start" in test else test.t.min()
        train = df[df.t < t0]
        if train.station_id.nunique() < 3 or test.empty: continue
        mdl = CensoredAR1(train).fit(n_em=4)
        for _, r in test.iterrows():
            if r.station_id not in mdl.st: continue
            pr = mdl.predict(r.station_id, r.t)
            if pr is None: continue
            m, s, t_last = pr
            j = np.where(mdl.si == mdl.st.index(r.station_id))[0][-1]
            persist = mdl.y_imp[j]
            q10, q90 = m + s * NORM.ppf(0.1), m + s * NORM.ppf(0.9)
            if r.censor == "none":
                cover = float(q10 <= r.lo <= q90); err = r.lo - m; err_p = r.lo - persist
            else:
                cover, err, err_p = np.nan, np.nan, np.nan
            out.append(dict(network=nw, origin_round=k, station_id=r.station_id, station_id_pcd=r.station_id_pcd,
                            t_target=str(r.t.date()), t_last_train=str(pd.Timestamp(t_last).date()),
                            horizon_days=int((r.t - pd.Timestamp(t_last)).days),
                            value_reported=r.value_reported, value_low=r.value_low, value_high=r.value_high,
                            censor=r.censor,
                            obs_ln=r.lo if r.censor == "none" else np.nan, pred_ln_mean=m, pred_ln_sd=s,
                            err_ln=err, err_ln_persistence=err_p, cover80=cover,
                            p_exceed=float(NORM.sf((np.log(THR) - m) / s)), exceed_obs=outcome_exceed(r)))
    return pd.DataFrame(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qc", default="A,B", help="ระดับคุณภาพข้อมูลที่ใช้ เช่น A หรือ A,B หรือ A,B,C")
    ap.add_argument("--target-date", default=None, help="วันที่พยากรณ์ YYYY-MM-DD (ค่าเริ่มต้น = วันข้อมูลล่าสุด + 28 วัน)")
    args = ap.parse_args()
    qc = [x.strip() for x in args.qc.split(",")]
    OUT.mkdir(parents=True, exist_ok=True)

    df = load(qc)
    run_id = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    cutoff = df.t.max()
    target = pd.Timestamp(args.target_date) if args.target_date else cutoff + pd.Timedelta(days=PAR["default_forecast_gap_days"])

    # 1) ทดสอบย้อนหลังก่อน เพื่อหาค่าปรับเทียบความกว้างช่วง (calibration factor k)
    val = rolling_validation(df, PAR["validation_start_round"])
    v = val.dropna(subset=["err_ln"])
    z = np.abs(v.err_ln / v.pred_ln_sd)
    k_cal = float(max(1.0, np.quantile(z, 0.8) / NORM.ppf(0.9))) if len(v) >= 20 else 1.0

    # 2) ฟิตด้วยข้อมูลทั้งหมดแล้วพยากรณ์
    mdl = CensoredAR1(df).fit()
    a, mu, rho, sig = mdl.unpack(mdl.th)
    rows = []
    # วันเป้าหมายแยกตามเครือข่าย = วันข้อมูลล่าสุดของเครือข่าย + ช่วงห่างกลางระหว่างรอบของเครือข่ายนั้น
    net_of = df.drop_duplicates("station_id").set_index("station_id")["network"].to_dict()
    targets = {}
    for nw, d in df.groupby("network"):
        tt = np.sort(d.t.unique())
        gap = PAR["default_forecast_gap_days"] if nw == "kok_basin" or len(tt) < 3 else int(np.median(np.diff(tt)).astype("timedelta64[D]").astype(int))
        targets[nw] = (pd.Timestamp(tt[-1]) + pd.Timedelta(days=gap)) if not args.target_date else target
    for s in mdl.st:
        if f"{s}_v2" in mdl.st:
            continue  # จุดเดิมก่อนย้าย ไม่พยากรณ์ต่อ
        target_s = targets.get(net_of.get(s, "kok_basin"), target)
        m, sd, t_last = mdl.predict(s, target_s)
        if (target_s - t_last).days > 200:
            continue  # สถานีที่หยุดเก็บนานแล้ว (เช่น SAL01-07 ตรวจครั้งเดียว) ไม่พยากรณ์
        sd = sd * k_cal
        n = int((df.station_id == s).sum())
        rec = dict(station_id=s.split("_v")[0], model_station_key=s, network=net_of.get(s, "kok_basin"),
                   target_date=str(target_s.date()), last_obs_date=str(t_last.date()),
                   horizon_days=int((target_s - t_last).days), n_obs=n, **summarize(m, sd),
                   unit="mg/L", is_measured=False, model="censored_logAR1_v1", qc_levels="".join(qc),
                   run_id=run_id, data_cutoff=str(cutoff.date()),
                   reliability="low" if n < PAR["min_obs_per_station"] or (target_s - t_last).days > 120 else "normal")
        # พยากรณ์ล่วงหน้าหลายรอบ (h = 1, 2, 3 รอบของเครือข่าย) — ทดสอบย้อนหลังแล้วเฉพาะ h = 1
        # นับรอบตามตารางเก็บตัวอย่างของเครือข่าย (วันล่าสุดของเครือข่าย + h × ช่วงห่างปกติ) ไม่ใช่จากวันล่าสุดของจุด
        nw_last = pd.Timestamp(df[df.network == net_of.get(s, "kok_basin")].t.max())
        gap_s = (target_s - nw_last).days
        hz = []
        for h in (1, 2, 3):
            th = nw_last + pd.Timedelta(days=gap_s * h) if gap_s > 0 else target_s
            mh, sdh, _ = mdl.predict(s, th)
            sdh = sdh * k_cal
            hz.append(dict(h=h, target_date=str(th.date()), horizon_days=int((th - t_last).days), **summarize(mh, sdh),
                           validated=(h == 1), reliability="low" if (th - t_last).days > 120 else "normal"))
        rec["horizons"] = hz
        rows.append(rec)
    fc = pd.DataFrame(rows)
    fc.to_csv(OUT / "forecast_latest.csv", index=False)
    payload = {"run_id": run_id, "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
               "data_cutoff": str(cutoff.date()), "target_date": str(target.date()),
               "target_date_by_network": {k: str(v.date()) for k, v in targets.items()},
               "model": {"name": "censored_logAR1_v1", "rho_per_14d": float(rho), "sigma_log_stationary": float(sig),
                         "group_mean_mgL": {g: float(np.exp(v)) for g, v in zip(mdl.gr, mu)},
                         "interval_calibration_k": k_cal},
               "disclaimer": "ค่าพยากรณ์ไม่ใช่ค่าตรวจวัด ใช้เพื่อเฝ้าระวังเท่านั้น โปรดยืนยันกับกรมควบคุมมลพิษ กรมควบคุมโรค และการประปาในพื้นที่",
               "segment_forecast": rows}
    (OUT / "forecast_latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    A = fit_model_A(df)
    (OUT / "model_A_turbidity.json").write_text(json.dumps(A, ensure_ascii=False, indent=2), encoding="utf-8")

    val.to_csv(OUT / "validation_rolling.csv", index=False)
    b = val.dropna(subset=["exceed_obs"])
    summary = {
        "n_point_tests": int(len(v)),
        "rmse_ln_model": float(np.sqrt(np.mean(v.err_ln ** 2))),
        "rmse_ln_persistence": float(np.sqrt(np.mean(v.err_ln_persistence ** 2))),
        "coverage80_raw": float(v.cover80.mean()),
        "interval_calibration_k": k_cal,
        "coverage80_after_k_in_sample": float((z <= k_cal * NORM.ppf(0.9)).mean()),
        "n_exceed_tests": int(len(b)),
        "brier_model": float(np.mean((b.p_exceed - b.exceed_obs) ** 2)),
        "brier_climatology": float(np.mean((b.exceed_obs.mean() - b.exceed_obs) ** 2)),
    }
    def _sub(vv, bb):
        return {"n_point_tests": int(len(vv)),
                "rmse_ln_model": float(np.sqrt(np.mean(vv.err_ln ** 2))) if len(vv) else None,
                "rmse_ln_persistence": float(np.sqrt(np.mean(vv.err_ln_persistence ** 2))) if len(vv) else None,
                "n_exceed_tests": int(len(bb)),
                "brier_model": float(np.mean((bb.p_exceed - bb.exceed_obs) ** 2)) if len(bb) else None,
                "hit_rate_p50": float(((bb.p_exceed >= 0.5) == (bb.exceed_obs == 1)).mean()) if len(bb) else None}
    summary["by_network"] = {nw: _sub(v[v.network == nw], b[b.network == nw]) for nw in sorted(val.network.unique())}
    (OUT / "validation_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"run_id={run_id} data_cutoff={cutoff.date()} target={target.date()}")
    print(f"rho(14d)={rho:.3f}  sigma_log={sig:.3f}  k_cal={k_cal:.3f}")
    print("Model A beta(ln turbidity) =", round(A["beta_ln_turbidity"], 3), "CI95", [round(x, 3) for x in A["ci95"]])
    print("validation:", json.dumps(summary, ensure_ascii=False))
    print(fc[["station_id", "last_obs_date", "horizon_days", "p10", "p50", "p90", "prob_exceed", "reliability"]]
          .to_string(index=False, float_format=lambda x: f"{x:.4f}"))


if __name__ == "__main__":
    main()
