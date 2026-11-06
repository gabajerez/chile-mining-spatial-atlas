from pathlib import Path
import pandas as pd
import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "enmc"
OUT.mkdir(parents=True, exist_ok=True)

matrix = pd.read_csv(
    OUT / "26_matriz_revision_proyectos_enmc.csv",
    encoding="utf-8-sig",
    dtype={"fila_xls": "string"},
    keep_default_na=False
)

co = gpd.read_file(
    ROOT / "Cartera de proyecto COCHILCO.shp",
    ignore_geometry=True,
    engine="pyogrio"
)

co["fila_xls"] = co["fila_xls"].astype("string")
matrix["fila_xls"] = matrix["fila_xls"].astype("string")

if co["fila_xls"].duplicated().any():
    raise ValueError("fila_xls duplicado en COCHILCO")

if matrix["fila_xls"].duplicated().any():
    raise ValueError("fila_xls duplicado en matriz 26")

fields = [
    "fila_xls", "proyecto", "proy_seia",
    "pres_seia", "ex_sea", "url_sea",
    "enlace_txt", "inc_mapa",
    "oa_geoms", "obs_geo",
    "met_pto", "prec_pto"
]

fields = [f for f in fields if f in co.columns]

co = co[fields].copy()

# No duplicar nombres de columnas ya existentes
extra = [
    f for f in fields
    if f == "fila_xls" or f not in matrix.columns
]

result = matrix.merge(
    co[extra],
    on="fila_xls",
    how="left",
    validate="one_to_one",
    indicator=True
)

if len(result) != 55 or not (result["_merge"] == "both").all():
    raise ValueError("Error de correspondencia matriz-COCHILCO")

result = result.drop(columns="_merge")

def has_value(value):
    return str(value).strip().lower() not in {
        "", "nan", "none", "null", "sin informacion",
        "sin información", "no informado"
    }

result["tiene_url_sea"] = (
    result["url_sea"].map(has_value)
    if "url_sea" in result.columns else False
)

result["tiene_referencia_seia"] = (
    result["proy_seia"].map(has_value)
    if "proy_seia" in result.columns else False
)

result["tiene_enlace_adicional"] = (
    result["enlace_txt"].map(has_value)
    if "enlace_txt" in result.columns else False
)

result["n_oa_dentro_filtro_enmc"] = pd.to_numeric(
    result["n_oa_dentro_filtro_enmc"],
    errors="coerce"
).fillna(0).astype(int)

result["n_geometrias_oa_referidas"] = pd.to_numeric(
    result["n_geometrias_oa_referidas"],
    errors="coerce"
).fillna(0).astype(int)

def prioritize(row):
    if (
        row["tipo_proyecto"] == "Nuevo"
        and row["n_geometrias_oa_referidas"] == 0
    ):
        return "P1_NUEVO_SIN_OA"

    if row["n_geometrias_oa_referidas"] == 0:
        return "P2_SIN_OA"

    if (
        row["n_oa_dentro_filtro_enmc"]
        < row["n_geometrias_oa_referidas"]
    ):
        return "P3_REVISAR_ASOCIACION_OA"

    return "P4_VERIFICAR_HUELLA_ADICIONAL"

result["prioridad"] = result.apply(prioritize, axis=1)

result["geometria_nueva_verificada"] = "NO"
result["ruta_geometria_nueva"] = ""
result["fuente_geometria"] = ""
result["decision_territorial"] = "PENDIENTE"

result = result.sort_values(
    ["prioridad", "region", "proyecto"]
)

dest = OUT / "27_fuentes_geometrias_proyectos.csv"
result.to_csv(dest, index=False, encoding="utf-8-sig")

print("=== AUDITORIA DE GEOMETRIAS ENMC ===")
print("Total:", len(result))

print("\nPrioridades:")
print(result["prioridad"].value_counts().sort_index())

print("\nReferencias disponibles:")
for field in [
    "tiene_url_sea",
    "tiene_referencia_seia",
    "tiene_enlace_adicional"
]:
    print(field, int(result[field].sum()))

print("\nPrimeros proyectos prioritarios:")
cols = [
    "proyecto", "mineral_original",
    "prioridad", "tiene_url_sea",
    "tiene_referencia_seia"
]
print(result[cols].head(20).to_string(index=False))

print("\nArchivo:", dest)
print("PASO 27 FINALIZADO")
