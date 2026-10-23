from pathlib import Path
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed"
TABLES = ROOT / "outputs/tables"
OUT = ROOT / "outputs/maps/regionales_comunas"

OUT.mkdir(parents=True, exist_ok=True)

print("=== MAPAS COMUNALES POR REGION ===", flush=True)

# --- Cargar datos ---
comunas = gpd.read_file(
    DATA / "comunas_consolidadas.gpkg",
    engine="pyogrio"
)

stats = pd.read_csv(
    TABLES / "matriz_mineria_comunal_v1.csv",
    dtype={"codreg": str, "codcom": str}
)

comunas["codreg"] = comunas["codreg"].astype(str).str.zfill(2)
comunas["codcom"] = comunas["codcom"].astype(str).str.zfill(5)
stats["codreg"] = stats["codreg"].astype(str).str.zfill(2)
stats["codcom"] = stats["codcom"].astype(str).str.zfill(5)

# Validaciones
if comunas["codcom"].duplicated().any():
    raise ValueError("Codigos comunales duplicados en cartografia")

if stats["codcom"].duplicated().any():
    raise ValueError("Codigos comunales duplicados en estadisticas")

gdf = comunas.merge(
    stats.drop(columns=["nomreg", "nomcom"], errors="ignore"),
    on=["codreg", "codcom"],
    how="left",
    validate="one_to_one",
    indicator=True
)

if not (gdf["_merge"] == "both").all():
    missing = gdf.loc[gdf["_merge"] != "both", "codcom"].tolist()
    raise ValueError(f"Comunas sin estadisticas: {missing[:10]}")

gdf = gdf.drop(columns="_merge")

if len(gdf) != 343:
    raise ValueError("Se esperaban 343 comunas")

# Nombres limpios por codigo regional
region_names = {
    "15": "Arica y Parinacota",
    "01": "Tarapaca",
    "02": "Antofagasta",
    "03": "Atacama",
    "04": "Coquimbo",
    "05": "Valparaiso",
    "13": "Metropolitana",
    "06": "O'Higgins",
    "07": "Maule",
    "16": "Nuble",
    "08": "Biobio",
    "09": "La Araucania",
    "14": "Los Rios",
    "10": "Los Lagos",
    "11": "Aysen",
    "12": "Magallanes"
}

# Variables para mapear
# oa_pct y concesiones_pct se recalculan para asegurar consistencia
gdf["oa_pct"] = gdf["oa_ha"] / gdf["superficie_comunal_ha"] * 100
gdf["concesiones_pct"] = (
    gdf["concesiones_constituidas_ha"] /
    gdf["superficie_comunal_ha"] * 100
)

map_specs = [
    ("oa_pct", "Cobertura OA (%)", "Blues"),
    ("concesiones_pct", "Concesiones constituidas (%)", "Oranges"),
    ("union_total_pct", "Cobertura integrada (%)", "YlOrRd"),
    ("cochilco_n", "Proyectos COCHILCO (n)", "Purples")
]

# Escalas globales para comparabilidad entre regiones
global_max = {}
for col, _, _ in map_specs:
    vmax = float(gdf[col].fillna(0).max())
    global_max[col] = max(vmax, 1e-9)

index_rows = []

# --- Generar un PNG por region ---
for codreg in sorted(gdf["codreg"].unique()):

    sub = gdf.loc[gdf["codreg"] == codreg].copy()

    if sub.empty:
        continue

    region_name = region_names.get(codreg, f"Region_{codreg}")

    xmin, ymin, xmax, ymax = sub.total_bounds
    dx = xmax - xmin
    dy = ymax - ymin

    # Margen
    padx = dx * 0.08 if dx > 0 else 1000
    pady = dy * 0.08 if dy > 0 else 1000

    fig, axes = plt.subplots(
        2, 2, figsize=(14, 16)
    )

    fig.subplots_adjust(
        left=0.04,
        right=0.96,
        top=0.91,
        bottom=0.09,
        wspace=0.18,
        hspace=0.32
    )

    for ax, (col, title, cmap_name) in zip(axes.flat, map_specs):

        sub.plot(
            column=col,
            ax=ax,
            cmap=cmap_name,
            edgecolor="#555555",
            linewidth=0.5,
            vmin=0,
            vmax=global_max[col],
            missing_kwds={
                "color": "#f0f0f0",
                "edgecolor": "#999999",
                "label": "Sin datos"
            }
        )

        ax.set_xlim(xmin - padx, xmax + padx)
        ax.set_ylim(ymin - pady, ymax + pady)
        ax.set_aspect("equal")
        ax.set_axis_off()
        ax.set_title(title, fontsize=13, weight="bold", pad=10)

        sm = ScalarMappable(
            norm=Normalize(vmin=0, vmax=global_max[col]),
            cmap=plt.get_cmap(cmap_name)
        )
        sm.set_array([])

        cbar = fig.colorbar(
            sm,
            ax=ax,
            orientation="horizontal",
            fraction=0.035,
            pad=0.07
        )
        cbar.ax.tick_params(labelsize=8)

    fig.suptitle(
        f"{region_name} | Indicadores comunales de actividad minera",
        fontsize=18,
        weight="bold"
    )

    fig.text(
        0.5, 0.025,
        "Fuentes: OA, SERNAGEOMIN, COCHILCO | Cartografia administrativa 2022",
        ha="center",
        fontsize=9
    )

    region_slug = region_name.lower().replace(" ", "_").replace("'", "").replace(".", "")
    filename = f"{codreg}_{region_slug}_dashboard_comunal.png"
    path = OUT / filename

    fig.savefig(
        path,
        dpi=220,
        bbox_inches="tight",
        facecolor="white"
    )
    plt.close(fig)

    index_rows.append({
        "codreg": codreg,
        "region": region_name,
        "archivo_png": filename,
        "n_comunas": len(sub)
    })

    print(f"Generado: {filename}", flush=True)

# Guardar indice
pd.DataFrame(index_rows).to_csv(
    OUT / "index_mapas_regionales_comunales.csv",
    index=False,
    encoding="utf-8-sig"
)

print("\n=== CONTROL ===")
print("Regiones procesadas:", len(index_rows))
print("Comunas cartografiadas:", len(gdf))
print("Indice generado:", OUT / "index_mapas_regionales_comunales.csv")
print("\nMAPAS REGIONALES COMUNALES FINALIZADOS", flush=True)

