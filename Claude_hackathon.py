import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# ── Daten laden ──────────────────────────────────────────────────────────────
df = pd.read_csv("Daten_Hackathon.csv", parse_dates=["timestamp"])
df.columns = df.columns.str.strip()
df = df.sort_values("timestamp").reset_index(drop=True)

# ── Modellparameter ───────────────────────────────────────────────────────────
dt         = 300
C          = 5.0e7
R          = 0.014
Tin0       = 20.0
Tin_set    = 20.0
Tin_min    = 18.0
Tin_max    = 22.0
QWP_max    = 10_000
Emax_th    = 7.0 * 3.6e6
Eth0       = 3.5 * 3.6e6
Pth_max    = 10_000
Ebat_max   = 10.0 * 3.6e6
Ebat0      = 5.0 * 3.6e6
Pbat_max   = 5_000
APV        = 100
eta_PV     = 0.20

# COP(Tout) = a − b·Tout  mit a=3.5, b=−0.10 → = 3.5 + 0.10·Tout
def COP(Tout):
    return max(1.5, 3.5 + 0.10 * Tout)

p25 = df["Strompreis [€/kWh]"].quantile(0.25)
p75 = df["Strompreis [€/kWh]"].quantile(0.75)

n    = len(df)
Tin  = np.zeros(n);  Tin[0]  = Tin0
Eth  = np.zeros(n);  Eth[0]  = Eth0
Ebat = np.zeros(n);  Ebat[0] = Ebat0
QWP  = np.zeros(n)
Pel  = np.zeros(n)
Pbat = np.zeros(n)
PPV  = np.zeros(n)
Pbuy = np.zeros(n)
Psell= np.zeros(n)
Q_space_arr = np.zeros(n)

for i in range(n):
    row   = df.iloc[i]
    Tout  = row["Aussentemperatur [°C]"]
    GHI   = row["GHI"]
    price = row["Strompreis [€/kWh]"]
    Pload = row["Bedarf_elektrisch [W]"]
    Qdem  = row["Bedarf_thermisch [W]"]     # Gesamter thermischer Bedarf [W]
    Qsol  = row["Solarthermie_Erzeugung [W]"]

    cop_i  = COP(Tout)
    PPV[i] = GHI * APV * eta_PV

    tin_i  = Tin[i]
    eth_i  = Eth[i]
    ebat_i = Ebat[i]
    eth_soc = eth_i / Emax_th
    ebat_soc= ebat_i / Ebat_max

    # ══════════════════════════════════════════════════════════════════════
    # Raumheizungsbedarf (RC-Modell): wie viel Wärme braucht das Gebäude?
    # Wenn Tout > Tin_set → kein Raumheizungsbedarf (Gebäude kühlt nicht ab)
    # Steady-state Verlust bei Tin_set: (Tin_set - Tout) / R
    # ══════════════════════════════════════════════════════════════════════
    q_space_need = max(0.0, (Tin_set - Tout) / R)   # [W] Heizbedarf Gebäude
    q_dhw        = max(0.0, Qdem - q_space_need)     # Rest = Warmwasser etc.

    # Thermischer Speicher liefert Raumwärme (+ Solar ergänzt)
    q_space_avail = min(q_space_need, eth_i / dt + Qsol)
    q_space_del   = q_space_avail
    Q_space_arr[i]= q_space_del

    # ── WP-Regelstrategie ─────────────────────────────────────────────────
    need_heat = (tin_i < Tin_min + 0.5) or (eth_soc < 0.15)
    can_store = eth_soc < 0.90

    if need_heat:
        wp_frac = 1.0
    elif price < 0 and can_store:
        wp_frac = 1.0
    elif price <= p25 and can_store:
        wp_frac = 0.75
    elif tin_i < Tin_min + 1.5 or eth_soc < 0.25:
        wp_frac = 0.5
    elif price >= p75:
        wp_frac = 0.0    # Teuer → WP aus, Speicher liefert
    else:
        wp_frac = 0.3

    # WP nicht über Speicherkapazität hinaus laden
    qwp_max_th = (Emax_th - eth_i) / dt + Qdem   # Speicher + aktueller Verbrauch
    qwp_i = np.clip(QWP_max * wp_frac, 0, min(QWP_max, qwp_max_th))
    pel_i = qwp_i / cop_i

    QWP[i] = qwp_i
    Pel[i] = pel_i

    # ── Thermischer Speicher ──────────────────────────────────────────────
    # Bilanz: WP + Solar → Speicher → Raumheizung + DHW
    eth_new = eth_i + (qwp_i + Qsol - Qdem) * dt
    eth_new = np.clip(eth_new, 0, Emax_th)

    # ── Batterie ──────────────────────────────────────────────────────────
    pnet_pre = Pload + pel_i - PPV[i]

    if pnet_pre < 0:
        # PV-Überschuss → Batterie laden
        pbat_i = min(-pnet_pre, Pbat_max, (1 - ebat_soc) * Ebat_max / dt)
    elif price < 0 and ebat_soc < 0.95:
        pbat_i = min(Pbat_max, (1 - ebat_soc) * Ebat_max / dt)
    elif price <= p25 and ebat_soc < 0.80:
        pbat_i = min(Pbat_max * 0.6, (1 - ebat_soc) * Ebat_max / dt)
    elif price >= p75 and ebat_soc > 0.20:
        pbat_i = -min(pnet_pre, Pbat_max, ebat_soc * Ebat_max / dt)
    else:
        pbat_i = 0

    Pbat[i] = pbat_i
    ebat_new = np.clip(ebat_i + pbat_i * dt, 0, Ebat_max)

    # ── Netz ─────────────────────────────────────────────────────────────
    pnet_i   = Pload + pel_i + pbat_i - PPV[i]
    Pbuy[i]  = max(0,  pnet_i)
    Psell[i] = max(0, -pnet_i)

    # ── Gebäudetemperatur (RC-Modell) ─────────────────────────────────────
    # NUR Raumheizung geht in die Temperaturdynamik ein!
    if i < n - 1:
        dTin     = ((Tout - tin_i) / R + q_space_del) / C * dt
        Tin[i+1]  = tin_i + dTin
        Eth[i+1]  = eth_new
        Ebat[i+1] = ebat_new

# ── DataFrame-Spalten ─────────────────────────────────────────────────────────
df["Tin"]      = Tin
df["Eth_kWh"]  = Eth  / 3.6e6
df["Ebat_kWh"] = Ebat / 3.6e6
df["QWP_kW"]   = QWP  / 1000
df["Pel_kW"]   = Pel  / 1000
df["Pbat_kW"]  = Pbat / 1000
df["PPV_kW"]   = PPV  / 1000
df["Pbuy_kW"]  = Pbuy / 1000
df["Psell_kW"] = Psell/ 1000

dt_h = dt / 3600

# ── KPIs ─────────────────────────────────────────────────────────────────────
cost_buy  = (df["Pbuy_kW"]  * df["Strompreis [€/kWh]"] * dt_h).sum()
revenue   = (df["Psell_kW"] * df["Strompreis [€/kWh]"] * dt_h).sum()
gewinn    = revenue - cost_buy

E_load   = (df["Bedarf_elektrisch [W]"] / 1000 * dt_h).sum()
E_wp     = (df["Pel_kW"]  * dt_h).sum()
E_pv     = (df["PPV_kW"]  * dt_h).sum()
E_buy    = (df["Pbuy_kW"] * dt_h).sum()
E_sell   = (df["Psell_kW"]* dt_h).sum()
E_total  = E_load + E_wp
autarkie = (E_total - E_buy) / E_total * 100

comfort_ok   = ((Tin >= Tin_min) & (Tin <= Tin_max)).mean() * 100

print(f"{'═'*55}")
print(f"  HACKATHON KPIs – Simulation Apr–Sep 2019")
print(f"{'═'*55}")
print(f"  Finanzieller Gewinn:   {gewinn:>10.2f} €")
print(f"  └─ Stromkosten:        {cost_buy:>10.2f} €")
print(f"  └─ Einspeiseerlös:     {revenue:>10.2f} €")
print(f"  Autarkiegrad:          {autarkie:>10.1f} %")
print(f"  PV-Erzeugung:          {E_pv:>10.0f} kWh")
print(f"  Netzbezug:             {E_buy:>10.0f} kWh")
print(f"  Einspeisung:           {E_sell:>10.0f} kWh")
print(f"  WP-Stromverbrauch:     {E_wp:>10.0f} kWh")
print(f"  Komforteinhaltung:     {comfort_ok:>10.1f} %")
print(f"  Tin min / max:   {Tin.min():>6.1f} / {Tin.max():.1f} °C")
print(f"{'═'*55}")

# ── Plots ─────────────────────────────────────────────────────────────────────
plt.rcParams.update({"font.size": 9})
fig, axes = plt.subplots(5, 1, figsize=(15, 18), sharex=True)
fig.suptitle(
    f"Wärmepumpen-Regelung – Hackathon Simulation (Apr–Sep 2019)\n"
    f"Gewinn: {gewinn:.2f} €  |  Autarkie: {autarkie:.1f} %  |  Komfort: {comfort_ok:.1f} %",
    fontsize=12, fontweight="bold")
ts = df["timestamp"]

ax = axes[0]
ax.fill_between(ts, Tin_min, Tin_max, alpha=0.18, color="green", label="Komfortband (18–22 °C)")
ax.plot(ts, Tin, color="firebrick", lw=0.6, label="Innentemperatur Tin")
ax.plot(ts, df["Aussentemperatur [°C]"], color="steelblue", lw=0.4, alpha=0.6, label="Außentemperatur")
ax.axhline(20, color="gray", ls=":", lw=0.8)
ax.set_ylabel("°C"); ax.set_ylim(0, 30)
ax.legend(fontsize=8, loc="upper right"); ax.set_title("Temperaturen")

ax = axes[1]
ax.stackplot(ts, df["PPV_kW"], labels=["PV-Erzeugung"], colors=["gold"], alpha=0.7)
ax.plot(ts, df["Pel_kW"], color="royalblue", lw=0.6, label="WP Strom [kW]")
ax.plot(ts, df["Bedarf_elektrisch [W]"]/1000, color="gray", lw=0.5, alpha=0.7, label="Haushaltslast")
ax.set_ylabel("kW"); ax.legend(fontsize=8, loc="upper right")
ax.set_title("Erzeugungs- & Verbrauchsleistungen")

ax = axes[2]
ax.plot(ts, df["Ebat_kWh"], color="purple",    lw=0.8, label="Batterie [kWh]")
ax.plot(ts, df["Eth_kWh"],  color="darkorange", lw=0.8, label="Therm. Speicher [kWh]")
ax.axhline(10, color="purple",    ls=":", lw=0.5, alpha=0.4)
ax.axhline(7,  color="darkorange",ls=":", lw=0.5, alpha=0.4)
ax.set_ylabel("kWh"); ax.set_ylim(0, 12)
ax.legend(fontsize=8, loc="upper right"); ax.set_title("Speicherzustände")

ax = axes[3]
ax.fill_between(ts, 0, df["Pbuy_kW"],  where=df["Pbuy_kW"]>0,  alpha=0.7, color="#e63946", label="Netzbezug")
ax.fill_between(ts, 0, df["Psell_kW"], where=df["Psell_kW"]>0, alpha=0.7, color="#2a9d8f", label="Einspeisung")
ax.axhline(0, color="black", lw=0.5)
ax.set_ylabel("kW"); ax.legend(fontsize=8, loc="upper right")
ax.set_title("Netzbezug & Einspeisung")

ax = axes[4]
ps = df["Strompreis [€/kWh]"]
ax.fill_between(ts, ps, 0, where=ps<0, color="#e63946", alpha=0.5, label="Negativpreis")
ax.plot(ts, ps, color="steelblue", lw=0.6, label="EPEX Spot")
ax.axhline(p25, color="green", ls="--", lw=0.9, label=f"P25 = {p25:.4f} €/kWh")
ax.axhline(p75, color="red",   ls="--", lw=0.9, label=f"P75 = {p75:.4f} €/kWh")
ax.set_ylabel("€/kWh"); ax.set_xlabel("Zeit")
ax.legend(fontsize=8, loc="upper right"); ax.set_title("Dynamischer Strompreis (EPEX Spot)")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))

plt.tight_layout()
plt.savefig("hackathon_simulation.png", dpi=150, bbox_inches="tight")
plt.close()

# ── Detailwoche ───────────────────────────────────────────────────────────────
week = df[(df["timestamp"] >= "2019-04-01") & (df["timestamp"] < "2019-04-08")].copy()
fig2, axes2 = plt.subplots(4, 1, figsize=(13, 11), sharex=True)
fig2.suptitle("Detailansicht: 01.–07. April 2019", fontsize=12, fontweight="bold")
ts2 = week["timestamp"]

axes2[0].fill_between(ts2, 18, 22, alpha=0.15, color="green", label="Komfortband")
axes2[0].plot(ts2, week["Tin"], color="firebrick", lw=1.2, label="Tin [°C]")
axes2[0].plot(ts2, week["Aussentemperatur [°C]"], color="steelblue", lw=0.8, ls="--", label="Tout [°C]")
axes2[0].set_ylabel("°C"); axes2[0].legend(fontsize=8); axes2[0].set_title("Temperaturen")

axes2[1].stackplot(ts2, week["PPV_kW"], labels=["PV"], colors=["gold"], alpha=0.7)
axes2[1].plot(ts2, week["QWP_kW"], color="darkorange", lw=1, label="WP Wärme [kW]")
axes2[1].plot(ts2, week["Pel_kW"], color="royalblue",  lw=1, label="WP Strom [kW]")
axes2[1].set_ylabel("kW"); axes2[1].legend(fontsize=8); axes2[1].set_title("WP & PV")

axes2[2].plot(ts2, week["Ebat_kWh"], color="purple",    lw=1.2, label="Batterie [kWh]")
axes2[2].plot(ts2, week["Eth_kWh"],  color="darkorange", lw=1.2, label="Therm. Sp. [kWh]")
axes2[2].set_ylabel("kWh"); axes2[2].legend(fontsize=8); axes2[2].set_title("Speicher")

axes2[3].fill_between(ts2, 0, week["Pbuy_kW"],  where=week["Pbuy_kW"]>0,  alpha=0.7, color="#e63946", label="Bezug")
axes2[3].fill_between(ts2, 0, week["Psell_kW"], where=week["Psell_kW"]>0, alpha=0.7, color="#2a9d8f", label="Einsp.")
ax2b = axes2[3].twinx()
ax2b.plot(ts2, week["Strompreis [€/kWh]"], color="black", lw=0.8, ls="--", label="Preis")
ax2b.set_ylabel("€/kWh")
axes2[3].set_ylabel("kW"); axes2[3].legend(fontsize=8, loc="upper left")
ax2b.legend(fontsize=8, loc="upper right")
axes2[3].set_title("Netz & Preis")
axes2[3].xaxis.set_major_formatter(mdates.DateFormatter("%a %d.%m."))
plt.setp(axes2[3].xaxis.get_majorticklabels(), rotation=30)

plt.tight_layout()
plt.savefig("hackathon_woche.png", dpi=150, bbox_inches="tight")
plt.close()
print("Done.")
