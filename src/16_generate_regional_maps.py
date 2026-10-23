from pathlib import Path
import geopandas as gpd
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed"
TABLES = ROOT / "outputs/tables"
OUT = ROOT / "outputs/maps"
OUT.mkdir(parents=True, exist_ok=True)

print("=== GENERACION MAPAS REGIONALES ===", flush=True)

regions = gpd.read_file(
    DATA / "regiones_consolidadas.gpkg",
    engine="pyogrio"
)

stats = pd.read_csv(
    TABLES / "matriz_mineria_regional_v1.csv",
    dtype={"codreg": str}
)

regions["codreg"] = regions["codreg"].astype(str).str.zfill(2)
stats["codreg"] = stats["codreg"].str.zfill(2)

if regions["codreg"].duplicated().any():
    raise ValueError("Regiones duplicadas en cartografia")

if stats["codreg"].duplicated().any():
    raise ValueError("Regiones duplicadas en estadisticas")

gdf = regions.merge(
    stats.drop(columns=["nomreg"], errors="ignore"),
    on="codreg",
    how="left",
    validate="one_to_one",
    indicator=True
)

if not (gdf["_merge"] == "both").all():
    raise ValueError("Regiones sin estadisticas")

gdf = gdf.drop(columns="_merge")

if len(gdf) != 16:
    raise ValueError("Se esperaban 16 regiones")

maps = [
    (
        "01_cobertura_oa_regional.png",
        "oa_ha",
        "Superficie OA por region",
        "Hectareas",
        "Blues"
    ),
    (
        "02_cobertura_concesiones_regional.png",
        "concesiones_constituidas_ha",
        "Concesiones constituidas por region",
        "Hectareas",
        "Oranges"
    ),
    (
        "03_cobertura_integrada_regional.png",
        "union_total_pct",
        "Cobertura territorial integrada",
        "% de superficie regional",
        "YlOrRd"
    ),
    (
        "04_proyectos_cochilco_regional.png",
        "cochilco_n",
        "Cartera COCHILCO por region",
        "Numero de proyectos",
        "Purples"
    )
]

# Convertir primer y segundo mapa a porcentajes regionales
gdf["oa_pct"] = (
    gdf["oa_ha"] / gdf["superficie_comunal_ha"] * 100
)
gdf["concesiones_pct"] = (
    gdf["concesiones_constituidas_ha"] /
    gdf["superficie_comunal_ha"] * 100
)

maps[0] = (
    "01_cobertura_oa_regional.png",
    "oa_pct",
    "Cobertura territorial OA",
    "% de superficie regional",
    "Blues"
)

maps[1] = (
    "02_cobertura_concesiones_regional.png",
    "concesiones_pct",
    "Cobertura de concesiones constituidas",
    "% de superficie regional",
    "Oranges"
)

for filename, column, title, label, cmap_name in maps:

    fig, ax = plt.subplots(figsize=(9, 12))

    gdf.plot(
        column=column,
        ax=ax,
        cmap=cmap_name,
        edgecolor="#444444",
        linewidth=0.35,
        legend=False,
        vmin=0,
        vmax=float(gdf[column].max())
    )

    norm = Normalize(
        vmin=0,
        vmax=max(float(gdf[column].max()), 1e-9)
    )

    sm = ScalarMappable(
        norm=norm,
        cmap=plt.get_cmap(cmap_name)
    )
    sm.set_array([])

    fig.colorbar(
        sm,
        ax=ax,
        orientation="horizontal",
        fraction=0.025,
        pad=0.04,
        label=label
    )

    ax.set_title(title, fontsize=15, weight="bold", pad=18)
    ax.set_axis_off()
    ax.set_aspect("equal")

    fig.text(
        0.5, 0.035,
        "Fuentes: OA, SERNAGEOMIN, COCHILCO | "
        "Cartografia administrativa 2022",
        ha="center",
        fontsize=8
    )

    path = OUT / filename
    fig.savefig(
        path, dpi=220, bbox_inches="tight",
        facecolor="white"
    )
    plt.close(fig)

    print("Generado:", path.name, flush=True)

print("\n=== CONTROL ===")
print("Regiones cartografiadas:", len(gdf))
print("Proyectos COCHILCO:",
      int(gdf["cochilco_n"].sum()))

print("\nMAPAS FINALIZADOS", flush=True)
