from pathlib import Path
import re
import unicodedata
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely

ROOT = Path(__file__).resolve().parents[1]

RAW_OA = ROOT / "OA-2-Articulo.shp"
RAW_COCH = ROOT / "Cartera de proyecto COCHILCO.shp"

COMMUNES = ROOT / "data" / "processed" / "comunas_consolidadas.gpkg"
REGIONS = ROOT / "data" / "processed" / "regiones_consolidadas.gpkg"
CONCESSIONS = ROOT / "data" / "processed" / "concesiones_final_6933.gpkg"

OUT_TABLES = ROOT / "outputs" / "tables"
OUT_MAPS = ROOT / "outputs" / "maps" / "estrategicos"
OUT_PROC = ROOT / "data" / "processed"

OUT_TABLES.mkdir(parents=True, exist_ok=True)
OUT_MAPS.mkdir(parents=True, exist_ok=True)

TARGET_CRS = "EPSG:6933"

print("=== MODULO MINERALES ESTRATEGICOS ===", flush=True)

def normalize_text(value):
    if pd.isna(value):
        return ""
    text = str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text)
    return text

def build_search_text(df, preferred_cols=None):
    preferred_cols = preferred_cols or []
    cols = [c for c in preferred_cols if c in df.columns]
    if not cols:
        cols = [c for c in df.columns if df[c].dtype == "object" and c != df.geometry.name]
    if not cols:
        raise ValueError("No se encontraron columnas de texto para clasificar.")

    text = (
        df[cols]
        .fillna("")
        .astype(str)
        .agg(" | ".join, axis=1)
        .map(normalize_text)
    )
    return text, cols

def classify_strategic(text):
    has_litio = "litio" in text
    has_ree = any(x in text for x in ["tierra rara", "tierras raras", "tierras ra", "rare earth"])

    if has_litio and has_ree:
        return "litio + tierras raras"
    if has_litio:
        return "litio"
    if has_ree:
        return "tierras raras"
    return None

# --------------------------------------------------
# Cargar capas
# --------------------------------------------------
oa = gpd.read_file(RAW_OA, engine="pyogrio")
coch = gpd.read_file(RAW_COCH, engine="pyogrio")
comunas = gpd.read_file(COMMUNES, engine="pyogrio")
regiones = gpd.read_file(REGIONS, engine="pyogrio")
conces = gpd.read_file(CONCESSIONS, engine="pyogrio")

for gdf_name, gdf in [("OA", oa), ("COCHILCO", coch), ("COMUNAS", comunas), ("REGIONES", regiones), ("CONCESIONES", conces)]:
    if gdf.crs is None:
        raise ValueError(f"{gdf_name} no tiene CRS.")
    if str(gdf.crs) != TARGET_CRS:
        gdf.to_crs(TARGET_CRS, inplace=True)


# Seleccionar concesiones constituidas
if "SITUACION_CONCESION" not in conces.columns:
    raise ValueError("Falta SITUACION_CONCESION")

conces = conces.loc[
    conces["SITUACION_CONCESION"]
    .astype(str).str.strip().str.upper() == "CONSTITUIDA"
].copy()

if conces.empty:
    raise ValueError("No se encontraron concesiones constituidas")

print("Concesiones constituidas:", len(conces), flush=True)

# --------------------------------------------------
# Clasificacion OA
# --------------------------------------------------
oa_text, oa_cols = build_search_text(
    oa,
    preferred_cols=["Mineral", "MINERAL", "minerales", "mineral", "SUSTANCIA", "sustancia", "RECURSO", "recurso"]
)
oa["strategic_class"] = oa_text.map(classify_strategic)
oa_sel = oa[oa["strategic_class"].notna()].copy()

if oa_sel.empty:
    raise ValueError("No se encontraron poligonos OA de litio o tierras raras.")

oa_sel["oa_area_ha"] = oa_sel.geometry.area / 10000.0

# --------------------------------------------------
# Clasificacion COCHILCO
# --------------------------------------------------
coch_text, coch_cols = build_search_text(
    coch,
    preferred_cols=["Mineral", "MINERAL", "minerales", "mineral"]
)
coch["strategic_class"] = coch_text.map(classify_strategic)
coch_sel = coch[coch["strategic_class"].notna()].copy()

if coch_sel.empty:
    raise ValueError("No se encontraron proyectos COCHILCO de litio o tierras raras.")

# nombre de proyecto
project_name_col = None
for cand in ["proyecto", "Proyecto", "PROYECTO", "Nombre", "NOMBRE", "project", "name"]:
    if cand in coch_sel.columns:
        project_name_col = cand
        break

if project_name_col is None:
    coch_sel["project_name"] = [f"Proyecto_{i+1}" for i in range(len(coch_sel))]
else:
    coch_sel["project_name"] = coch_sel[project_name_col].astype(str)

# --------------------------------------------------
# Coincidencia con concesiones SIN doble conteo
# --------------------------------------------------

oa_sel = oa_sel.reset_index(drop=True)
oa_sel["oa_id_tmp"] = np.arange(1, len(oa_sel) + 1)

# Reparar geometr?as OA antes de medir
oa_sel["geometry"] = oa_sel.geometry.map(
    lambda g: shapely.make_valid(g)
    if g is not None and not g.is_valid else g
)

oa_sel["oa_area_ha"] = oa_sel.geometry.area / 10000.0

idx_con = conces.sindex
overlaps = []

for _, row in oa_sel.iterrows():
    geom = row.geometry
    ids = idx_con.query(geom, predicate="intersects")

    if len(ids) == 0:
        overlaps.append(0.0)
        continue

    partes = []
    for candidate in conces.geometry.iloc[ids]:
        inter = geom.intersection(candidate)
        if not inter.is_empty:
            partes.append(inter)

    if partes:
        # Uni?n: elimina superficies duplicadas
        union_inter = shapely.union_all(partes)
        union_inter = union_inter.intersection(geom)
        area = union_inter.area / 10000.0
    else:
        area = 0.0

    overlaps.append(area)

oa_sel["overlap_ha"] = overlaps

oa_sel["overlap_pct"] = np.where(
    oa_sel["oa_area_ha"] > 0,
    oa_sel["overlap_ha"] / oa_sel["oa_area_ha"] * 100,
    0
)

oa_sel["intersecta_concesion"] = oa_sel["overlap_ha"] > 0

if (
    oa_sel["overlap_ha"] >
    oa_sel["oa_area_ha"] + 0.001
).any():
    raise ValueError(
        "La superficie de interseccion excede el area OA"
    )

# Un proyecto se cuenta una sola vez aunque coincida
# con varias concesiones
coch_sel = coch_sel.reset_index(drop=True)

coch_sel["en_concesion"] = [
    bool(len(idx_con.query(
        geom, predicate="intersects"
    )))
    for geom in coch_sel.geometry
]

print(
    "Control OA: maximo porcentaje de superposicion:",
    round(float(oa_sel["overlap_pct"].max()), 4)
)

# --------------------------------------------------
# Asignacion comuna / region
# --------------------------------------------------
# OA por comuna mediante interseccion espacial exacta
oa_com = gpd.overlay(
    oa_sel[["oa_id_tmp", "strategic_class", "geometry"]],
    comunas[["codreg", "codcom", "nomreg", "nomcom", "geometry"]],
    how="intersection",
    keep_geom_type=False
)
oa_com["oa_area_ha"] = oa_com.geometry.area / 10000.0

oa_strategic_comunal = (
    oa_com.groupby(["codreg", "codcom", "nomreg", "nomcom", "strategic_class"], as_index=False)
    .agg(oa_area_ha=("oa_area_ha", "sum"))
    .sort_values(["codreg", "codcom", "strategic_class"])
)

oa_strategic_regional = (
    oa_strategic_comunal.groupby(["codreg", "nomreg", "strategic_class"], as_index=False)
    .agg(oa_area_ha=("oa_area_ha", "sum"))
    .sort_values(["codreg", "strategic_class"])
)

# COCHILCO por comuna / region
coch_com = gpd.sjoin(
    coch_sel[["project_name", "strategic_class", "en_concesion", "geometry"]],
    comunas[["codreg", "codcom", "nomreg", "nomcom", "geometry"]],
    how="left",
    predicate="within"
).drop(columns=["index_right"], errors="ignore")

coch_projects = (
    coch_com[["project_name", "strategic_class", "en_concesion", "codreg", "codcom", "nomreg", "nomcom"]]
    .sort_values(["strategic_class", "nomreg", "nomcom", "project_name"])
)

coch_regional = (
    coch_projects.groupby(["codreg", "nomreg", "strategic_class"], as_index=False)
    .agg(
        n_proyectos=("project_name", "count"),
        n_proyectos_en_concesion=("en_concesion", "sum")
    )
    .sort_values(["codreg", "strategic_class"])
)

# --------------------------------------------------
# Resumen nacional
# --------------------------------------------------
oa_summary = (
    oa_sel.groupby("strategic_class", as_index=False)
    .agg(
        n_poligonos=("oa_id_tmp", "count"),
        superficie_ha=("oa_area_ha", "sum"),
        superficie_overlap_concesion_ha=("overlap_ha", "sum")
    )
)
oa_summary["pct_overlap_concesion"] = np.where(
    oa_summary["superficie_ha"] > 0,
    oa_summary["superficie_overlap_concesion_ha"] / oa_summary["superficie_ha"] * 100,
    0
)

coch_summary = (
    coch_sel.groupby("strategic_class", as_index=False)
    .agg(
        n_proyectos=("project_name", "count"),
        n_proyectos_en_concesion=("en_concesion", "sum")
    )
)
coch_summary["pct_proyectos_en_concesion"] = np.where(
    coch_summary["n_proyectos"] > 0,
    coch_summary["n_proyectos_en_concesion"] / coch_summary["n_proyectos"] * 100,
    0
)

national = oa_summary.merge(coch_summary, on="strategic_class", how="outer")

# --------------------------------------------------
# Guardar outputs
# --------------------------------------------------
oa_sel.to_file(OUT_PROC / "oa_minerales_estrategicos.gpkg", layer="oa_estrategicos", driver="GPKG")
coch_sel.to_file(OUT_PROC / "cochilco_minerales_estrategicos.gpkg", layer="cochilco_estrategicos", driver="GPKG")

# concesiones relacionadas: las que intersectan OA o contienen proyectos
conces_oa = gpd.sjoin(conces, oa_sel[["geometry"]], how="inner", predicate="intersects").drop(columns=["index_right"], errors="ignore")
conces_coch = gpd.sjoin(conces, coch_sel[["geometry"]], how="inner", predicate="contains").drop(columns=["index_right"], errors="ignore")
conces_rel = pd.concat([conces_oa, conces_coch], ignore_index=True)
conces_rel = gpd.GeoDataFrame(conces_rel, geometry="geometry", crs=conces.crs)
conces_rel = conces_rel.loc[~conces_rel.geometry.to_wkb().duplicated()].copy()
if not conces_rel.empty:
    conces_rel.to_file(OUT_PROC / "concesiones_minerales_estrategicos.gpkg", layer="concesiones_estrategicos", driver="GPKG")

oa_sel.drop(columns="geometry").to_csv(OUT_TABLES / "oa_minerales_estrategicos_poligonos.csv", index=False, encoding="utf-8-sig")
oa_strategic_comunal.to_csv(OUT_TABLES / "oa_minerales_estrategicos_comunal.csv", index=False, encoding="utf-8-sig")
oa_strategic_regional.to_csv(OUT_TABLES / "oa_minerales_estrategicos_regional.csv", index=False, encoding="utf-8-sig")

coch_projects.to_csv(OUT_TABLES / "cochilco_minerales_estrategicos_proyectos.csv", index=False, encoding="utf-8-sig")
coch_regional.to_csv(OUT_TABLES / "cochilco_minerales_estrategicos_regional.csv", index=False, encoding="utf-8-sig")

national.to_csv(OUT_TABLES / "resumen_minerales_estrategicos_nacional.csv", index=False, encoding="utf-8-sig")

print("\n=== CONTROL ===")
print("Columnas usadas en OA:", oa_cols)
print("Columnas usadas en COCHILCO:", coch_cols)
print("Poligonos OA filtrados:", len(oa_sel))
print("Proyectos COCHILCO filtrados:", len(coch_sel))
print("Clases OA:", oa_sel["strategic_class"].value_counts(dropna=False).to_dict())
print("Clases COCHILCO:", coch_sel["strategic_class"].value_counts(dropna=False).to_dict())

print("\n=== RESUMEN NACIONAL ===")
print(national.to_string(index=False))

print("\nArchivos generados:")
print("- outputs/tables/oa_minerales_estrategicos_poligonos.csv")
print("- outputs/tables/oa_minerales_estrategicos_comunal.csv")
print("- outputs/tables/oa_minerales_estrategicos_regional.csv")
print("- outputs/tables/cochilco_minerales_estrategicos_proyectos.csv")
print("- outputs/tables/cochilco_minerales_estrategicos_regional.csv")
print("- outputs/tables/resumen_minerales_estrategicos_nacional.csv")
print("- data/processed/oa_minerales_estrategicos.gpkg")
print("- data/processed/cochilco_minerales_estrategicos.gpkg")
print("- data/processed/concesiones_minerales_estrategicos.gpkg (si hubo coincidencias)")

print("\nMODULO FINALIZADO", flush=True)
