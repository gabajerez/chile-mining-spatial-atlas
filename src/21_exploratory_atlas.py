from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "outputs/tables"
OUT = ROOT / "outputs/figures/atlas"
OUT.mkdir(parents=True, exist_ok=True)

com = pd.read_csv(
    TABLES / "matriz_cobre_comunal_v1.csv",
    dtype={"codreg": str, "codcom": str}
)

reg = pd.read_csv(
    TABLES / "matriz_mineria_regional_v1.csv",
    dtype={"codreg": str}
)

cobre_reg = pd.read_csv(
    TABLES / "matriz_cobre_regional_v1.csv",
    dtype={"codreg": str}
)

names = {
    "01": "Tarapacá",
    "02": "Antofagasta",
    "03": "Atacama",
    "04": "Coquimbo",
    "05": "Valparaíso",
    "06": "O'Higgins",
    "07": "Maule",
    "08": "Biobío",
    "09": "La Araucanía",
    "10": "Los Lagos",
    "11": "Aysén",
    "12": "Magallanes",
    "13": "Metropolitana",
    "14": "Los Ríos",
    "15": "Arica y Parinacota",
    "16": "Ñuble"
}

for df in [com, reg, cobre_reg]:
    df["codreg"] = df["codreg"].str.zfill(2)
    df["region"] = df["codreg"].map(names)

if len(com) != 343 or len(reg) != 16:
    raise ValueError("Dimensiones inesperadas")

if com["codcom"].nunique() != 343:
    raise ValueError("Codigos comunales duplicados")

if not set(reg.codreg) == set(cobre_reg.codreg):
    raise ValueError("Regiones incompatibles")


required = [
    "oa_ha",
    "concesiones_constituidas_ha",
    "superficie_comunal_ha",
    "union_total_ha",
    "union_total_pct",
    "cobre_total_ha",
    "cobre_pct_comunal",
    "cochilco_n",
    "cochilco_cobre_n"
]

missing = [col for col in required if col not in com.columns]

if missing:
    raise ValueError(
        f"Columnas faltantes en matriz comunal: {missing}"
    )

print("Columnas comunales validadas.", flush=True)

print("=== ATLAS ESTADISTICO ===", flush=True)

# =====================================================
# FIGURA 1: COBERTURA REGIONAL
# =====================================================

reg["oa_pct"] = (
    reg["oa_ha"] / reg["superficie_comunal_ha"] * 100
)

reg["concesiones_pct"] = (
    reg["concesiones_constituidas_ha"] /
    reg["superficie_comunal_ha"] * 100
)

d = reg.sort_values("union_total_pct")

fig, ax = plt.subplots(figsize=(12, 9))

y = np.arange(len(d))
h = 0.25

ax.barh(
    y - h, d["oa_pct"], height=h,
    label="OA", color="#377eb8"
)
ax.barh(
    y, d["concesiones_pct"], height=h,
    label="Concesiones", color="#e68a35"
)
ax.barh(
    y + h, d["union_total_pct"], height=h,
    label="Integrada", color="#16877b"
)

ax.set_yticks(y, d["region"])
ax.set_xlabel("Cobertura territorial (%)")
ax.set_title(
    "Cobertura minera por región y fuente",
    weight="bold", fontsize=15
)
ax.legend(loc="lower right")
ax.grid(axis="x", alpha=0.15)
ax.set_axisbelow(True)
ax.spines[["top", "right"]].set_visible(False)

fig.tight_layout()
fig.savefig(
    OUT / "01_comparacion_cobertura_regional.png",
    dpi=220, facecolor="white"
)
plt.close(fig)

print("Figura 1 generada.", flush=True)

# =====================================================
# FIGURA 2: RELACION COMUNAL OA / CONCESIONES
# =====================================================

fig, ax = plt.subplots(figsize=(10, 8))

x = (
    com["concesiones_constituidas_ha"]
    / com["superficie_comunal_ha"] * 100
).astype(float)
y = com["oa_ha"] / com["superficie_comunal_ha"] * 100

ax.scatter(
    x, y,
    s=28, alpha=0.55,
    edgecolors="none",
    color="#2878a8"
)

corr = x.corr(y, method="spearman")

ax.set_xlabel("Cobertura concesionada constituida (%)")
ax.set_ylabel("Cobertura OA (%)")
ax.set_title(
    "Relación entre cobertura OA y concesiones",
    weight="bold", fontsize=15
)
ax.grid(alpha=0.15)

ax.text(
    0.03, 0.95,
    f"n = {len(com)} comunas\nSpearman rho = {corr:.3f}",
    transform=ax.transAxes,
    va="top",
    fontsize=11
)

fig.tight_layout()
fig.savefig(
    OUT / "02_relacion_oa_concesiones_comunal.png",
    dpi=220, facecolor="white"
)
plt.close(fig)

print("Figura 2 generada.", flush=True)

# =====================================================
# FIGURA 3: SUPERFICIE COBRE POR REGION
# =====================================================

d = cobre_reg.sort_values("cobre_total_ha")

fig, ax = plt.subplots(figsize=(11, 9))

ax.barh(
    d["region"], d["cobre_total_ha"],
    color="#b76d35"
)

ax.set_xlabel("Superficie vinculada al cobre OA (ha)")
ax.set_title(
    "Distribución regional de superficie asociada al cobre",
    weight="bold", fontsize=14
)
ax.grid(axis="x", alpha=0.15)
ax.set_axisbelow(True)
ax.spines[["top", "right"]].set_visible(False)

fig.tight_layout()
fig.savefig(
    OUT / "03_superficie_cobre_regional.png",
    dpi=220, facecolor="white"
)
plt.close(fig)

print("Figura 3 generada.", flush=True)

# =====================================================
# TABLAS Y ESTADISTICAS
# =====================================================

variables = [
    "oa_ha",
    "concesiones_constituidas_ha",
    "union_total_ha",
    "union_total_pct",
    "cobre_total_ha",
    "cobre_pct_comunal",
    "cochilco_n",
    "cochilco_cobre_n"
]

describe = (
    com[variables]
    .describe(percentiles=[0.25, 0.5, 0.75, 0.9, 0.95])
    .T
)

describe.to_csv(
    TABLES / "atlas_estadisticas_descriptivas.csv",
    encoding="utf-8-sig"
)

rankings = {
    "cobertura_integrada": "union_total_pct",
    "superficie_concesionada": "concesiones_constituidas_ha",
    "superficie_oa": "oa_ha",
    "superficie_cobre": "cobre_total_ha",
    "cobertura_cobre": "cobre_pct_comunal",
    "proyectos_cochilco": "cochilco_n"
}

for name, column in rankings.items():

    ranking = (
        com.sort_values(column, ascending=False)
        .head(20)
        .copy()
    )

    ranking.insert(
        0, "ranking", range(1, len(ranking) + 1)
    )

    ranking[[
        "ranking", "codreg", "codcom",
        "nomreg", "nomcom", column
    ]].to_csv(
        TABLES / f"atlas_top20_{name}.csv",
        index=False,
        encoding="utf-8-sig"
    )

print("\n=== CONTROLES ===")
print("Comunas:", len(com))
print("Regiones:", len(reg))
print("Superficie cobre (ha):",
      round(com["cobre_total_ha"].sum(), 2))
print("Correlacion Spearman:", round(corr, 4))
print("Figuras generadas: 3")
print("Rankings generados:", len(rankings))

print("\nATLAS EXPLORATORIO FINALIZADO", flush=True)
