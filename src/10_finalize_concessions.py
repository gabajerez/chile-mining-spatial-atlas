from pathlib import Path
import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
TABLES = ROOT / "outputs" / "tables"

SOURCE = PROCESSED / "concesiones_6933.gpkg"
FIXES = PROCESSED / "concesiones_reparaciones.gpkg"
DEST = PROCESSED / "concesiones_final_6933.gpkg"
TEMP = PROCESSED / "concesiones_final_6933.tmp.gpkg"

print("=== CONSOLIDACION DE CONCESIONES ===", flush=True)

con = gpd.read_file(SOURCE, engine="pyogrio")
fix = gpd.read_file(FIXES, engine="pyogrio")

print("Concesiones originales:", len(con))
print("Reparaciones:", len(fix))

if con.crs != fix.crs:
    raise ValueError("CRS diferentes entre capas")

if len(con) != 104147:
    raise ValueError("Cantidad inesperada de concesiones")

if con["ID_CONCESION"].duplicated().any():
    raise ValueError("Identificadores duplicados")

if fix["ID_CONCESION"].duplicated().any():
    raise ValueError("Identificadores duplicados en reparaciones")

original_invalid = set(
    con.loc[~con.geometry.is_valid, "ID_CONCESION"].astype(str)
)

fixed_ids = set(fix["ID_CONCESION"].astype(str))

if original_invalid != fixed_ids:
    raise ValueError(
        "Las reparaciones no corresponden exactamente "
        "a las geometrías inválidas"
    )

# Sustituir exclusivamente geometrías identificadas
con = con.set_index("ID_CONCESION", drop=False)
fix = fix.set_index("ID_CONCESION", drop=False)

for cid in fix.index:
    con.at[cid, "geometry"] = fix.at[cid, "geometry"]

con = con.reset_index(drop=True)

# Actualizar área geométrica
con["area_geom_ha"] = con.geometry.area / 10000

con["dif_area_ha"] = (
    con["area_geom_ha"] - con["area_decl_ha"]
)

con["dif_area_pct"] = (
    con["dif_area_ha"] /
    con["area_decl_ha"].where(con["area_decl_ha"] > 0)
    * 100
)

# Controles finales
invalid = int((~con.geometry.is_valid).sum())
empty = int(con.geometry.is_empty.sum())
null = int(con.geometry.isna().sum())
unique_ids = con["ID_CONCESION"].nunique()

print("\n=== CONTROL FINAL ===")
print("Registros:", len(con))
print("ID únicos:", unique_ids)
print("Geometrías inválidas:", invalid)
print("Geometrías vacías:", empty)
print("Geometrías nulas:", null)
print("CRS:", con.crs)

if invalid or empty or null:
    raise ValueError("Existen geometrías problemáticas")

if unique_ids != len(con):
    raise ValueError("Identificadores no únicos")

if con.crs.to_epsg() != 6933:
    raise ValueError("CRS distinto de EPSG:6933")

# Generar salida temporal antes de reemplazarla
if TEMP.exists():
    TEMP.unlink()

con.to_file(
    TEMP,
    layer="concesiones",
    driver="GPKG",
    engine="pyogrio",
    index=False
)

# Verificar salida escrita
check = gpd.read_file(
    TEMP,
    engine="pyogrio",
    columns=["ID_CONCESION"]
)

if len(check) != len(con):
    raise ValueError("Error en escritura del GeoPackage")

if (~check.geometry.is_valid).any():
    raise ValueError("Geometrías inválidas en archivo exportado")

TEMP.replace(DEST)

# Resumen estadístico
summary = (
    con.groupby(
        ["TIPO_CONCESION", "SITUACION_CONCESION"],
        dropna=False
    )
    .agg(
        n_concesiones=("ID_CONCESION", "nunique"),
        hectareas_geometricas=("area_geom_ha", "sum"),
        hectareas_declaradas=("area_decl_ha", "sum")
    )
    .reset_index()
)

summary.to_csv(
    TABLES / "concesiones_final_control.csv",
    index=False,
    encoding="utf-8-sig"
)

print("\n=== RESUMEN POR SITUACION ===")
print(summary.to_string(index=False))

print("\nARCHIVO FINAL:", DEST)
print("PROCESO FINALIZADO", flush=True)
