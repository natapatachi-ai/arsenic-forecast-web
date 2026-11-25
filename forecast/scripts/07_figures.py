"""07_figures.py  สร้างรูปผลลัพธ์สำหรับรายงานโครงงาน -> results/fig*.png"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter, LogLocator
DEC = FuncFormatter(lambda v, _: f"{v:g}")


def decimal_log(ax, axis="y"):
    a = ax.yaxis if axis == "y" else ax.xaxis
    a.set_major_locator(LogLocator(base=10, subs=(1, 2, 5)))
    a.set_major_formatter(DEC)
    a.set_minor_formatter(FuncFormatter(lambda v, _: ""))

ROOT = Path(__file__).resolve().parents[1]
P, F, OUT = ROOT / "data" / "processed", ROOT / "data" / "forecast", ROOT / "results"
OUT.mkdir(exist_ok=True)
for name in ["Loma", "Sarabun", "TH Sarabun New", "Tahoma", "Leelawadee UI"]:
    if any(name in f.name for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = [name, "DejaVu Sans"]
        break
plt.rcParams.update({"axes.unicode_minus": False, "mathtext.fontset": "dejavusans", "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 150})
STD = 0.01
C_OBS, C_FC, C_STD, C_CEN = "#1f4e79", "#c0504d", "#7f7f7f", "#9dc3e6"

fc = json.loads((F / "forecast_latest.json").read_text(encoding="utf-8"))
f = pd.DataFrame(fc["segment_forecast"])
f = f[f.reliability == "normal"].sort_values("prob_exceed")

# รูป 1 : โอกาสเกินมาตรฐานรอบถัดไป
fig, ax = plt.subplots(figsize=(8, 6.5))
ax.barh(f.station_id, f.prob_exceed, color=[C_FC if p >= 0.5 else C_OBS for p in f.prob_exceed])
for y, p in enumerate(f.prob_exceed):
    ax.text(p + 0.01, y, f"{p:.0%}", va="center", fontsize=8)
ax.axvline(0.5, color=C_STD, ls="--", lw=1)
ax.set_xlim(0, 1.05)
ax.set_xlabel("ความน่าจะเป็นที่สารหนูเกิน 0.01 มก./ล.")
ax.set_title(f"พยากรณ์รอบถัดไป (เป้าหมาย {fc['target_date']}) จากข้อมูลถึง {fc['data_cutoff']}\nค่าพยากรณ์ ไม่ใช่ค่าตรวจวัด", fontsize=11)
fig.tight_layout(); fig.savefig(OUT / "fig1_prob_exceed_next_round.png"); plt.close(fig)

# รูป 2 : อนุกรมเวลาค่าตรวจวัด + ช่วงพยากรณ์ 4 สถานี
w = pd.read_csv(P / "water_arsenic_long.csv", parse_dates=["t_mid"])
fa = pd.DataFrame(fc["segment_forecast"]).set_index("station_id")
fig, axes = plt.subplots(2, 2, figsize=(11, 7), sharex=True)
for ax, sid in zip(axes.ravel(), ["SA01", "KK01", "RU01", "NK01"]):
    d = w[w.station_id == sid].sort_values("t_mid")
    pt = d[d.censor == "none"]; cen = d[d.censor == "left"]
    ax.plot(pt.t_mid, pt.value, "o-", color=C_OBS, ms=3.5, lw=1, label="ค่าตรวจวัด (คพ.)")
    ax.scatter(cen.t_mid, cen.value_high, marker="v", color=C_CEN, s=22, zorder=3, label="< 0.010 (ต่ำกว่าขีดตรวจวัด)")
    t = pd.Timestamp(fa.loc[sid, "target_date"])
    ax.errorbar([t], [fa.loc[sid, "p50"]], yerr=[[fa.loc[sid, "p50"] - fa.loc[sid, "p10"]], [fa.loc[sid, "p90"] - fa.loc[sid, "p50"]]],
                fmt="s", color=C_FC, capsize=4, label="พยากรณ์ P50 (P10–P90)")
    ax.axhline(STD, color=C_STD, ls="--", lw=1)
    ax.set_yscale("log"); decimal_log(ax); ax.set_title(sid, fontsize=10)
    ax.set_ylabel("สารหนู (มก./ล.)")
axes[0, 0].legend(fontsize=7, loc="upper right")
fig.suptitle("สารหนูในน้ำผิวดินรอบ 1–24 และค่าพยากรณ์รอบถัดไป (เส้นประ = มาตรฐาน 0.01 มก./ล.)", fontsize=11)
fig.autofmt_xdate(); fig.tight_layout(); fig.savefig(OUT / "fig2_timeseries_forecast.png"); plt.close(fig)

# รูป 3 : ทดสอบย้อนหลัง
v = pd.read_csv(F / "validation_rolling.csv").dropna(subset=["err_ln"])
s = json.loads((F / "validation_summary.json").read_text())
fig, ax = plt.subplots(1, 2, figsize=(11, 4.5))
ax[0].scatter(v.pred_ln_mean, v.obs_ln, s=10, alpha=.6, color=C_OBS)
lim = [min(v.pred_ln_mean.min(), v.obs_ln.min()) - .2, max(v.pred_ln_mean.max(), v.obs_ln.max()) + .2]
ax[0].plot(lim, lim, color=C_STD, lw=1)
ax[0].set_xlabel("ln(ค่าพยากรณ์)"); ax[0].set_ylabel("ln(ค่าตรวจวัด)")
ax[0].set_title(f"ทดสอบย้อนหลัง n={s['n_point_tests']}  RMSE(ln) {s['rmse_ln_model']:.2f} "
                f"vs persistence {s['rmse_ln_persistence']:.2f}", fontsize=10)
b = pd.read_csv(F / "validation_rolling.csv").dropna(subset=["exceed_obs"])
bins = np.linspace(0, 1, 6); b["bin"] = pd.cut(b.p_exceed, bins, include_lowest=True)
g = b.groupby("bin", observed=True).agg(p=("p_exceed", "mean"), o=("exceed_obs", "mean"), n=("p_exceed", "size"))
ax[1].plot([0, 1], [0, 1], color=C_STD, lw=1)
ax[1].plot(g.p, g.o, "o-", color=C_FC)
for _, r in g.iterrows():
    ax[1].annotate(int(r.n), (r.p, r.o), textcoords="offset points", xytext=(4, -10), fontsize=7)
ax[1].set_xlabel("ความน่าจะเป็นที่พยากรณ์"); ax[1].set_ylabel("สัดส่วนที่เกินจริง")
ax[1].set_title(f"Reliability  Brier {s['brier_model']:.3f} vs climatology {s['brier_climatology']:.3f}", fontsize=10)
fig.tight_layout(); fig.savefig(OUT / "fig3_validation.png"); plt.close(fig)

# รูป 4 : ความขุ่นกับสารหนู (หลักฐานกลไก Kd·TSS)
m = pd.read_csv(P / "model_table.csv")
m = m[m.turbidity_NTU.notna()]
A = json.loads((F / "model_A_turbidity.json").read_text())
fig, ax = plt.subplots(figsize=(6.5, 4.8))
pt = m[m.censor == "none"]; cen = m[m.censor == "left"]
ax.scatter(pt.turbidity_NTU, pt.value, s=10, alpha=.6, color=C_OBS, label="ค่าตรวจวัด")
ax.scatter(cen.turbidity_NTU, cen.value_high, s=10, marker="v", color=C_CEN, label="< 0.010")
ax.axhline(STD, color=C_STD, ls="--", lw=1)
ax.set_xscale("log"); ax.set_yscale("log"); decimal_log(ax); decimal_log(ax, "x")
ax.set_xlabel("ความขุ่น (NTU)"); ax.set_ylabel("สารหนู (มก./ล.)")
ax.set_title(f"Tobit: β(ln ความขุ่น) = {A['beta_ln_turbidity']:.2f} (CI95 {A['ci95'][0]:.2f}–{A['ci95'][1]:.2f}), n={A['n_obs']}", fontsize=10)
ax.legend(fontsize=8)
fig.tight_layout(); fig.savefig(OUT / "fig4_turbidity_arsenic.png"); plt.close(fig)

f_all = pd.DataFrame(fc["segment_forecast"])[["station_id", "target_date", "last_obs_date", "horizon_days", "p10", "p50", "p90",
                                               "prob_exceed", "reliability", "is_measured", "run_id"]]
f_all.to_csv(OUT / "forecast_table.csv", index=False)
print("saved figures to", OUT)
