from pathlib import Path
import re
import unicodedata
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize, ListedColormap, BoundaryNorm
from matplotlib.cm import ScalarMappable

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed"
TABLES = ROOT / "outputs/tables"
OUT = ROOT / "outputs/maps/regionales_cobre"
OUT.mkdir(parents=True, exist_ok=True)

NAMES = {
    "01": "Tarapacá", "02": "Antofagasta",
    "03": "Atacama", "04": "Coquimbo",
    "05": "Valparaíso", "06": "O'Higgins",
    "07": "Maule", "08": "Biobío",
    "09": "La Araucanía", "10": "Los Lagos",
    "11": "Aysén", "12": "Magallanes",
    "13": "Metropolitana", "14": "Los Ríos",
    "15": "Arica y Parinacota", "16": "Ñuble"
}

def slug(value):
    text = unicodedata.normalize("NFKD", value)
    text = "".join(
        ch for ch in text
        if not unicodedata.combining(ch)
    )
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")

print("=== MAPAS COMUNALES DE COBRE ===", flush=True)

com = gpd.read_file(
    DATA / "comunas_consolidadas.gpkg",
    engine="pyogrio"
)

stats = pd.read_csv(
    TABLES / "matriz_cobre_comunal_v1.csv",
    dtype={"codreg": str, "codcom": str}
)

for frame in [com, stats]:
    frame["codreg"] = frame["codreg"].astype(str).str.zfill(2)
    frame["codcom"] = frame["codcom"].astype(str).str.zfill(5)

if com["codcom"].duplicated().any():
    raise ValueError("Codigos duplicados en geometria")

if stats["codcom"].duplicated().any():
    raise ValueError("Codigos duplicados en estadisticas")

gdf = com.merge(
    stats.drop(columns=["nomreg", "nomcom"], errors="ignore"),
    on=["codreg", "codcom"],
    how="left",
    validate="one_to_one",
    indicator=True
)

if len(gdf) != 343 or not (gdf["_merge"] == "both").all():
    raise ValueError("Integracion administrativa incompleta")

gdf = gdf.drop(columns="_merge")

if int(gdf["cochilco_cobre_n"].sum()) != 40:
    raise ValueError("Total COCHILCO cobre inesperado")

if abs(gdf["cobre_total_ha"].sum() - 185694.67) > 1:
    raise ValueError("Superficie de cobre inesperada")

# Escalas comunes a todas las regiones
max_pct = max(0.01, float(gdf["cobre_pct_comunal"].max()))
max_ha = max(1, float(gdf["cobre_total_ha"].max()))
max_projects = max(1, int(gdf["cochilco_cobre_n"].max()))

project_cmap = ListedColormap(
    plt.get_cmap("Purples")(
        [0.05] + [
            0.25 + 0.70 * i / max_projects
            for i in range(1, max_projects + 1)
        ]
    )
)
project_norm = BoundaryNorm(
    [i - 0.5 for i in range(max_projects + 2)],
    project_cmap.N
)

specs = [
    ("cobre_pct_comunal",
     "Cobertura territorial de cobre OA (%)",
     "Blues", 0, max_pct),
    ("cobre_total_ha",
     "Superficie asociada al cobre OA (ha)",
     "YlOrBr", 0, max_ha),
    ("cobre_pct_oa",
     "Participación del cobre dentro de OA (%)",
     "YlGn", 0, 100),
    ("cochilco_cobre_n",
     "Proyectos futuros de cobre COCHILCO (n)",
     "Purples", 0, max_projects)
]

index = []

for code in sorted(gdf["codreg"].unique()):

    sub = gdf[gdf["codreg"] == code].copy()
    name = NAMES[code]

    fig, axes = plt.subplots(2, 2, figsize=(15, 17))

    fig.subplots_adjust(
        left=0.06, right=0.96,
        top=0.91, bottom=0.10,
        wspace=0.16, hspace=0.34
    )

    xmin, ymin, xmax, ymax = sub.total_bounds
    dx, dy = xmax - xmin, ymax - ymin

    for ax, (col, title, cmap_name, vmin, vmax) in zip(
        axes.flat, specs
    ):
        if col == "cochilco_cobre_n":
            cmap = project_cmap
            norm = project_norm
        else:
            cmap = plt.get_cmap(cmap_name).copy()
            cmap.set_bad("#c9c9c9")
            norm = Normalize(vmin=vmin, vmax=vmax)

        sub.plot(
            column=col,
            ax=ax,
            cmap=cmap,
            norm=norm,
            edgecolor="#666666",
            linewidth=0.35,
            missing_kwds={
                "color": "#c9c9c9",
                "edgecolor": "#666666"
            }
        )

        ax.set_xlim(xmin - dx * 0.06, xmax + dx * 0.06)
        ax.set_ylim(ymin - dy * 0.06, ymax + dy * 0.06)
        ax.set_aspect("equal")
        ax.set_axis_off()
        ax.set_title(title, fontsize=12, weight="bold", pad=12)

        sm = ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])

        cb = fig.colorbar(
            sm, ax=ax, orientation="horizontal",
            fraction=0.035, pad=0.06
        )

        if col == "cochilco_cobre_n":
            cb.set_ticks(list(range(max_projects + 1)))

        cb.ax.tick_params(labelsize=8)


    fig.suptitle(
        f"{name} | Distribución comunal del cobre",
        fontsize=19, weight="bold", y=0.97
    )

    fig.text(
        0.5, 0.025,
        "Fuentes: OA y COCHILCO | Límites administrativos 2022\n"
        "Las superficies corresponden a polígonos OA asociados al cobre; "
        "no representan extracción efectiva.",
        ha="center", fontsize=9
    )

    filename = f"{code}_{slug(name)}_cobre_comunal.png"

    fig.savefig(
        OUT / filename,
        dpi=180,
        bbox_inches="tight",
        facecolor="white"
    )
    plt.close(fig)

    index.append({
        "codreg": code,
        "region": name,
        "n_comunas": len(sub),
        "n_comunas_con_cobre": int(
            (sub["cobre_total_ha"] > 0).sum()
        ),
        "cobre_ha": float(sub["cobre_total_ha"].sum()),
        "proyectos_cochilco_cobre": int(
            sub["cochilco_cobre_n"].sum()
        ),
        "archivo": filename
    })

    print(f"Generado: {filename}", flush=True)

pd.DataFrame(index).to_csv(
    OUT / "indice_mapas_cobre.csv",
    index=False,
    encoding="utf-8-sig"
)

print("\n=== CONTROL ===")
print("Regiones:", len(index))
print("Comunas:", len(gdf))
print("Comunas con cobre:", int((gdf["cobre_total_ha"] > 0).sum()))
print("Proyectos COCHILCO cobre:", int(gdf["cochilco_cobre_n"].sum()))
print("Mapas generados:", len(index))
print("\nPROCESO FINALIZADO", flush=True)
