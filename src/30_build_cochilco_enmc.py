from pathlib import Path
import pandas as pd
import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/processed/enmc"
REPORT = ROOT / "reports/enmc"

OUT.mkdir(parents=True, exist_ok=True)

source = ROOT / "Cartera de proyecto COCHILCO.shp"
matrix_path = REPORT / "27_fuentes_geometrias_proyectos.csv"

co = gpd.read_file(source, engine="pyogrio")
matrix = pd.read_csv(
    matrix_path,
    encoding="utf-8-sig",
    dtype=str,
    keep_default_na=False
)

if co.crs is None:
    raise ValueError("COCHILCO no tiene CRS")

def normalize_id(series):
    return series.astype("string").str.strip()

co["fila_xls"] = normalize_id(co["fila_xls"])
matrix["fila_xls"] = normalize_id(matrix["fila_xls"])

if co["fila_xls"].duplicated().any():
    raise ValueError("Identificadores COCHILCO duplicados")

if matrix["fila_xls"].duplicated().any():
    raise ValueError("Identificadores matriz duplicados")

fields = [
    "fila_xls",
    "minerales_enmc",
    "prioridad",
    "n_geometrias_oa_referidas",
    "n_oa_dentro_filtro_enmc"
]

projects = co.merge(
    matrix[fields],
    on="fila_xls",
    how="inner",
    validate="one_to_one"
)

if len(projects) != 55:
    raise ValueError(
        f"Esperados 55 proyectos; obtenidos {len(projects)}"
    )

if projects.geometry.isna().any():
    raise ValueError("Hay proyectos sin geometria")

projects = projects.to_crs("EPSG:4326")

if not projects.geometry.geom_type.eq("Point").all():
    raise ValueError("Hay geometrías COCHILCO que no son puntos")

projects["geometria_fuente"] = "PUNTO_COCHILCO"
projects["poligono_nuevo_validado"] = False
projects["superficie_nueva_ha"] = float("nan")

# Asegurar columnas compatibles con GeoPackage
for col in projects.columns:
    if col == projects.geometry.name:
        continue
    if pd.api.types.is_object_dtype(projects[col]):
        projects[col] = projects[col].astype("string").fillna("")

dest = OUT / "cochilco_enmc_proyectos.gpkg"

if dest.exists():
    dest.unlink()

projects.to_file(
    dest,
    layer="proyectos_enmc",
    driver="GPKG",
    engine="pyogrio"
)

summary = (
    projects.groupby("prioridad")
    .size()
    .reset_index(name="n_proyectos")
)

summary.to_csv(
    REPORT / "30_cochilco_enmc_resumen.csv",
    index=False,
    encoding="utf-8-sig"
)

print("=== PASO 30: COCHILCO ENMC ===")
print("Proyectos:", len(projects))
print(summary.to_string(index=False))
print("CRS:", projects.crs)
print("Capa:", dest)
print("PASO 30 FINALIZADO")
