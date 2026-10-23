from pathlib import Path
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "outputs/tables"
FIGURES = ROOT / "outputs/figures"
MAPS = ROOT / "outputs/maps"

FIGURES.mkdir(parents=True, exist_ok=True)
MAPS.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(
    TABLES / "matriz_mineria_regional_v1.csv",
    dtype={"codreg": str}
)

df["codreg"] = df["codreg"].str.zfill(2)

names = {
    "01": "Tarapaca",
    "02": "Antofagasta",
    "03": "Atacama",
    "04": "Coquimbo",
    "05": "Valparaiso",
    "06": "O'Higgins",
    "07": "Maule",
    "08": "Biobio",
    "09": "La Araucania",
    "10": "Los Lagos",
    "11": "Aysen",
    "12": "Magallanes",
    "13": "Metropolitana",
    "14": "Los Rios",
    "15": "Arica y Parinacota",
    "16": "Nuble"
}

df["region"] = df["codreg"].map(names)

area = df["superficie_comunal_ha"]

df["oa_pct"] = df["oa_ha"] / area * 100
df["concesiones_pct"] = (
    df["concesiones_constituidas_ha"] / area * 100
)
df["aporte_oa_pp"] = (
    df["oa_solo_ha"] / area * 100
)

# Validar identidad de cobertura
err = (
    df["union_total_pct"]
    - df["concesiones_pct"]
    - df["aporte_oa_pp"]
).abs().max()

if err > 1e-6:
    raise ValueError(f"Inconsistencia de porcentajes: {err}")

panels = [
    ("oa_pct", "Cobertura OA (%)", "#2563a6"),
    (
        "concesiones_pct",
        "Concesiones constituidas (%)",
        "#dd7527"
    ),
    (
        "aporte_oa_pp",
        "Aporte exclusivo OA (puntos porcentuales)",
        "#16877b"
    ),
    (
        "cochilco_n",
        "Proyectos COCHILCO (n)",
        "#7655a6"
    )
]

fig, axes = plt.subplots(
    2, 2, figsize=(17, 13),
    constrained_layout=True
)

for ax, (column, title, color) in zip(axes.flat, panels):
    data = df.sort_values(column, ascending=True)

    bars = ax.barh(
        data["region"],
        data[column],
        color=color,
        alpha=0.9
    )

    ax.set_title(title, fontsize=14, weight="bold", pad=14)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.grid(axis="x", alpha=0.18)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0, labelsize=9)

    vmax = max(float(data[column].max()), 0.01)
    ax.set_xlim(0, vmax * 1.2)

    for bar, val in zip(bars, data[column]):
        label = (
            f"{int(val)}"
            if column == "cochilco_n"
            else f"{val:.3f}" if column == "aporte_oa_pp"
            else f"{val:.2f}"
        )

        ax.text(
            bar.get_width() + vmax * 0.012,
            bar.get_y() + bar.get_height() / 2,
            label,
            va="center",
            fontsize=8
        )

fig.suptitle(
    "Actividad minera y cobertura territorial por region",
    fontsize=19,
    weight="bold"
)

fig.savefig(
    FIGURES / "01_dashboard_regional_mineria.png",
    dpi=220,
    bbox_inches="tight",
    facecolor="white"
)
plt.close(fig)

print("Panel regional generado.", flush=True)

# Mapa de incremento porcentual por OA
regions = gpd.read_file(
    ROOT / "data/processed/regiones_consolidadas.gpkg",
    engine="pyogrio"
)

regions["codreg"] = (
    regions["codreg"].astype(str).str.zfill(2)
)

gdf = regions.merge(
    df[["codreg", "aporte_oa_pp"]],
    on="codreg",
    how="left",
    validate="one_to_one"
)

if gdf["aporte_oa_pp"].isna().any():
    raise ValueError("Regiones sin datos")

fig, ax = plt.subplots(figsize=(9, 12))

max_val = float(gdf["aporte_oa_pp"].max())
norm = Normalize(vmin=0, vmax=max(max_val, 1e-9))

gdf.plot(
    column="aporte_oa_pp",
    ax=ax,
    cmap="YlGnBu",
    edgecolor="#555555",
    linewidth=0.3,
    norm=norm
)

sm = ScalarMappable(
    norm=norm,
    cmap=plt.get_cmap("YlGnBu")
)
sm.set_array([])

fig.colorbar(
    sm,
    ax=ax,
    orientation="horizontal",
    fraction=0.025,
    pad=0.04,
    label="Aporte exclusivo OA (puntos porcentuales)"
)

ax.set_title(
    "Superficie OA fuera de concesiones constituidas",
    fontsize=14,
    weight="bold",
    pad=15
)
ax.set_axis_off()

fig.text(
    0.5, 0.025,
    "Fuentes: OA y SERNAGEOMIN | "
    "Limites administrativos de referencia 2022",
    ha="center",
    fontsize=8
)

fig.savefig(
    MAPS / "05_aporte_exclusivo_oa_regional.png",
    dpi=220,
    bbox_inches="tight",
    facecolor="white"
)
plt.close(fig)

print("Mapa de aporte OA generado.", flush=True)

# Tabla de indicadores complementarios
df[[
    "codreg", "region", "oa_pct",
    "concesiones_pct", "union_total_pct",
    "aporte_oa_pp", "cochilco_n"
]].to_csv(
    TABLES / "indicadores_regionales_visualizacion.csv",
    index=False,
    encoding="utf-8-sig"
)

print("\n=== TOP APORTE EXCLUSIVO OA ===")
print(
    df.sort_values("aporte_oa_pp", ascending=False)
    [["region", "oa_solo_ha", "aporte_oa_pp"]]
    .head(10)
    .to_string(index=False)
)

print("\nVISUALIZACIONES FINALIZADAS", flush=True)
