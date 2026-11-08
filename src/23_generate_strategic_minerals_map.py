from pathlib import Path
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[1]

COMMUNES = ROOT / "data" / "processed" / "comunas_consolidadas.gpkg"
OA = ROOT / "data" / "processed" / "oa_minerales_estrategicos.gpkg"
COCH = ROOT / "data" / "processed" / "cochilco_minerales_estrategicos.gpkg"
CONCES_REL = ROOT / "data" / "processed" / "concesiones_minerales_estrategicos.gpkg"

OUT = ROOT / "outputs" / "maps" / "estrategicos"
OUT.mkdir(parents=True, exist_ok=True)

print("=== MAPA MINERALES ESTRATEGICOS ===", flush=True)

comunas = gpd.read_file(COMMUNES, engine="pyogrio")
oa = gpd.read_file(OA, layer="oa_estrategicos", engine="pyogrio")
coch = gpd.read_file(COCH, layer="cochilco_estrategicos", engine="pyogrio")

if CONCES_REL.exists():
    conces_rel = gpd.read_file(CONCES_REL, layer="concesiones_estrategicos", engine="pyogrio")
else:
    conces_rel = None

# separar clases
oa_litio = oa[oa["strategic_class"] == "litio"].copy()
oa_ree = oa[oa["strategic_class"] == "tierras raras"].copy()
oa_mix = oa[oa["strategic_class"] == "litio + tierras raras"].copy()

coch_litio = coch[coch["strategic_class"] == "litio"].copy()
coch_ree = coch[coch["strategic_class"] == "tierras raras"].copy()
coch_mix = coch[coch["strategic_class"] == "litio + tierras raras"].copy()

fig, axes = plt.subplots(1, 3, figsize=(20, 10))
fig.subplots_adjust(left=0.03, right=0.98, top=0.90, bottom=0.12, wspace=0.08)

xmin, ymin, xmax, ymax = comunas.total_bounds
dx, dy = xmax - xmin, ymax - ymin

def base(ax, title):
    comunas.boundary.plot(ax=ax, color="#9a9a9a", linewidth=0.25)
    if conces_rel is not None and not conces_rel.empty:
        conces_rel.plot(ax=ax, facecolor="#f4a261", edgecolor="#b5651d", linewidth=0.25, alpha=0.35)
    ax.set_xlim(xmin - dx * 0.03, xmax + dx * 0.03)
    ax.set_ylim(ymin - dy * 0.03, ymax + dy * 0.03)
    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.set_title(title, fontsize=14, weight="bold", pad=10)

# Panel 1: Litio
ax = axes[0]
base(ax, "Litio")
if not oa_litio.empty:
    oa_litio.plot(ax=ax, facecolor="#2b83ba", edgecolor="#084081", linewidth=0.8, alpha=0.85)
if not oa_mix.empty:
    oa_mix.plot(ax=ax, facecolor="#7bccc4", edgecolor="#0868ac", linewidth=0.8, alpha=0.85)
if not coch_litio.empty:
    coch_litio.plot(ax=ax, color="#08306b", marker="*", markersize=90, edgecolor="white", linewidth=0.6)
if not coch_mix.empty:
    coch_mix.plot(ax=ax, color="#225ea8", marker="P", markersize=75, edgecolor="white", linewidth=0.6)

# Panel 2: Tierras raras
ax = axes[1]
base(ax, "Tierras raras")
if not oa_ree.empty:
    oa_ree.plot(ax=ax, facecolor="#41ab5d", edgecolor="#005a32", linewidth=0.8, alpha=0.85)
if not oa_mix.empty:
    oa_mix.plot(ax=ax, facecolor="#7bccc4", edgecolor="#0868ac", linewidth=0.8, alpha=0.85)
if not coch_ree.empty:
    coch_ree.plot(ax=ax, color="#00441b", marker="*", markersize=90, edgecolor="white", linewidth=0.6)
if not coch_mix.empty:
    coch_mix.plot(ax=ax, color="#238b45", marker="P", markersize=75, edgecolor="white", linewidth=0.6)

# Panel 3: Integrado
ax = axes[2]
base(ax, "Litio + tierras raras")
if not oa_litio.empty:
    oa_litio.plot(ax=ax, facecolor="#2b83ba", edgecolor="#084081", linewidth=0.8, alpha=0.85)
if not oa_ree.empty:
    oa_ree.plot(ax=ax, facecolor="#41ab5d", edgecolor="#005a32", linewidth=0.8, alpha=0.85)
if not oa_mix.empty:
    oa_mix.plot(ax=ax, facecolor="#7bccc4", edgecolor="#0868ac", linewidth=0.8, alpha=0.85)
if not coch_litio.empty:
    coch_litio.plot(ax=ax, color="#08306b", marker="*", markersize=90, edgecolor="white", linewidth=0.6)
if not coch_ree.empty:
    coch_ree.plot(ax=ax, color="#00441b", marker="^", markersize=65, edgecolor="white", linewidth=0.6)
if not coch_mix.empty:
    coch_mix.plot(ax=ax, color="#225ea8", marker="P", markersize=75, edgecolor="white", linewidth=0.6)

# Etiquetas de proyectos en panel integrado
for _, row in coch.iterrows():
    pt = row.geometry
    if pt is not None and not pt.is_empty:
        axes[2].annotate(
            row["project_name"],
            xy=(pt.x, pt.y),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=7,
            color="#333333"
        )

legend_items = [
    Patch(facecolor="#f4a261", edgecolor="#b5651d", alpha=0.35, label="Concesiones coincidentes"),
    Patch(facecolor="#2b83ba", edgecolor="#084081", label="OA litio"),
    Patch(facecolor="#41ab5d", edgecolor="#005a32", label="OA tierras raras"),
    Patch(facecolor="#7bccc4", edgecolor="#0868ac", label="OA mixto"),
    Line2D([0], [0], marker="*", color="w", label="Proyecto COCHILCO litio",
           markerfacecolor="#08306b", markeredgecolor="white", markersize=12),
    Line2D([0], [0], marker="^", color="w", label="Proyecto COCHILCO tierras raras",
           markerfacecolor="#00441b", markeredgecolor="white", markersize=10),
    Line2D([0], [0], marker="P", color="w", label="Proyecto COCHILCO mixto",
           markerfacecolor="#225ea8", markeredgecolor="white", markersize=10),
]

fig.legend(
    handles=legend_items,
    loc="lower center",
    ncol=4,
    frameon=False,
    fontsize=9,
    bbox_to_anchor=(0.5, 0.04)
)

fig.suptitle(
    "Minerales estratégicos: litio y tierras raras\nPolígonos OA, proyectos COCHILCO y coincidencias con concesiones",
    fontsize=18,
    weight="bold",
    y=0.97
)

fig.text(
    0.5, 0.012,
    "Fuentes: OA, COCHILCO y SERNAGEOMIN | Límites administrativos 2022\n"
    "Las concesiones mostradas corresponden solo a coincidencias espaciales con los elementos estratégicos seleccionados.",
    ha="center", fontsize=9
)

out_path = OUT / "01_minerales_estrategicos_nacional.png"
fig.savefig(out_path, dpi=220, bbox_inches="tight", facecolor="white")
plt.close(fig)

print("Mapa generado:", out_path)
print("MAPA FINALIZADO", flush=True)
