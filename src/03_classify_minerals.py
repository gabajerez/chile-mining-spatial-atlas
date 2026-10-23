from pathlib import Path
import pandas as pd
import geopandas as gpd
import unicodedata
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "tables"
OUT.mkdir(parents=True, exist_ok=True)

def normalize(value):
    if pd.isna(value):
        return ""
    text = str(value).strip().upper()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        c for c in text if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", text)

def copper_class(value):
    value = normalize(value)

    if value == "COBRE":
        return "COBRE_EXCLUSIVO"

    if re.search(r"\bCOBRE\b", value):
        return "COBRE_ASOCIADO"

    return "SIN_COBRE_DECLARADO"

# OA
oa = gpd.read_file(
    ROOT / "OA-2-Articulo.shp",
    ignore_geometry=True,
    engine="pyogrio"
)

oa["region_norm"] = oa["REGION"].map(normalize)
oa["mineral_norm"] = oa["MINERAL"].map(normalize)
oa["clase_cobre"] = oa["MINERAL"].map(copper_class)

oa_summary = (
    oa.groupby(
        ["region_norm", "clase_cobre"],
        dropna=False
    )
    .size()
    .reset_index(name="n_registros")
)

oa_summary.to_csv(
    OUT / "oa_cobre_por_region.csv",
    index=False,
    encoding="utf-8-sig"
)

# COCHILCO
co = gpd.read_file(
    ROOT / "Cartera de proyecto COCHILCO.shp",
    ignore_geometry=True,
    engine="pyogrio"
)

co["region_norm"] = co["region"].map(normalize)
co["clase_cobre"] = co["Mineral"].map(copper_class)
co["mineral_critico_original"] = (
    co["Mineral cr"].fillna("NO INFORMADO")
)

co_summary = (
    co.groupby(
        [
            "region_norm",
            "clase_cobre",
            "mineral_critico_original"
        ],
        dropna=False
    )
    .agg(
        n_proyectos=("fila_xls", "nunique"),
        inversion_mmus=("inv_mmus", "sum")
    )
    .reset_index()
)

co_summary.to_csv(
    OUT / "cochilco_minerales_por_region.csv",
    index=False,
    encoding="utf-8-sig"
)

# Concesiones
con = gpd.read_file(
    ROOT / "sernageomin_concesiones_2026-06-05.geojson",
    ignore_geometry=True,
    engine="pyogrio"
)

con["comuna_norm"] = con["COMUNA"].map(normalize)

con_summary = (
    con.groupby(
        [
            "comuna_norm",
            "TIPO_CONCESION",
            "SITUACION_CONCESION"
        ],
        dropna=False
    )
    .agg(
        n_concesiones=("ID_CONCESION", "nunique"),
        hectareas_declaradas=("HECTAREAS", "sum")
    )
    .reset_index()
)

con_summary.to_csv(
    OUT / "concesiones_por_comuna.csv",
    index=False,
    encoding="utf-8-sig"
)

print("\n=== OA: CLASIFICACION COBRE ===")
print(oa["clase_cobre"].value_counts().to_string())

print("\n=== COCHILCO: CLASIFICACION COBRE ===")
print(co["clase_cobre"].value_counts().to_string())

print("\n=== COCHILCO: MINERAL CRITICO ORIGINAL ===")
print(
    co["mineral_critico_original"]
    .value_counts()
    .to_string()
)

print("\n=== ARCHIVOS GENERADOS ===")
for path in sorted(OUT.glob("*.csv")):
    print(path.name)
