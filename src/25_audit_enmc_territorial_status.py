from pathlib import Path
import pandas as pd
import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "enmc"
OUT.mkdir(parents=True, exist_ok=True)

OA = ROOT / "OA-2-Articulo.shp"
CO = ROOT / "Cartera de proyecto COCHILCO.shp"

def read_attributes(path):
    return gpd.read_file(
        path, engine="pyogrio",
        ignore_geometry=True
    )

def clean(series):
    return series.fillna("").astype(str).str.strip()

def audit_fields(df, fields, filename):
    rows = []

    for field in fields:
        if field not in df.columns:
            print(f"CAMPO AUSENTE: {field}")
            continue

        counts = (
            clean(df[field])
            .value_counts(dropna=False)
        )

        for value, n in counts.items():
            rows.append({
                "campo": field,
                "valor": value,
                "n": int(n)
            })

    result = pd.DataFrame(
        rows, columns=["campo", "valor", "n"]
    )

    result.to_csv(
        OUT / filename,
        index=False,
        encoding="utf-8-sig"
    )
    return result

# OA: utilizar la lista ya identificada en auditoría 24
oa_ids = pd.read_csv(
    ROOT / "reports/audit_enmc_oa_detalle.csv",
    encoding="utf-8-sig"
)

oa = read_attributes(OA)

if len(oa) != len(oa_ids):
    raise RuntimeError(
        "La cantidad de filas OA no coincide "
        "con la auditoría 24"
    )

oa["enmc_si"] = oa_ids["enmc_si"].to_numpy()
oa["minerales_enmc"] = (
    oa_ids["minerales_enmc"]
    .fillna("").to_numpy()
)

oa = oa[oa["enmc_si"] == True].copy()

print("\n=== OA ENMC ===")
print("Registros:", len(oa))

oa_fields = [
    "TIPO", "CAT_SERN",
    "SERN_FAENA", "SERN_INST",
    "SERN_REC", "TAM_EMP",
    "IST_100", "IST_01", "IST_ORIG",
    "S_AP", "S_SB", "S_GL",
    "S_HU", "S_AI", "S_CI",
    "S_AD", "S_PO", "S_TU"
]

oa_counts = audit_fields(
    oa, oa_fields,
    "25_oa_atributos.csv"
)

print("\nTIPO OA:")
print(
    oa_counts[
        oa_counts["campo"] == "TIPO"
    ].to_string(index=False)
)

print("\nCAT_SERN OA:")
print(
    oa_counts[
        oa_counts["campo"] == "CAT_SERN"
    ].to_string(index=False)
)

oa.to_csv(
    OUT / "25_oa_enmc_revision.csv",
    index=False,
    encoding="utf-8-sig"
)

# COCHILCO: utilizar selección de auditoría 24
co_ids = pd.read_csv(
    ROOT / "reports/audit_enmc_cochilco_detalle.csv",
    encoding="utf-8-sig"
)

co = read_attributes(CO)

if len(co) != len(co_ids):
    raise RuntimeError(
        "La cantidad de filas COCHILCO no "
        "coincide con auditoría 24"
    )

co["enmc_si"] = co_ids["enmc_si"].to_numpy()
co["minerales_enmc"] = (
    co_ids["minerales_enmc"]
    .fillna("").to_numpy()
)

co = co[co["enmc_si"] == True].copy()

print("\n=== COCHILCO ENMC ===")
print("Proyectos:", len(co))

co_fields = [
    "tipo_proy", "etapa",
    "condicion", "oa_estado",
    "oa_geoms", "inc_mapa",
    "met_pto", "prec_pto",
    "geo_uc"
]

co_counts = audit_fields(
    co, co_fields,
    "25_cochilco_atributos.csv"
)

for field in ["tipo_proy", "oa_estado", "oa_geoms"]:
    print(f"\n{field}:")
    print(
        co_counts[
            co_counts["campo"] == field
        ].to_string(index=False)
    )

co_review = [
    "fila_xls", "proyecto", "Mineral",
    "minerales_enmc", "empresa", "region",
    "tipo_proy", "etapa", "condicion",
    "oa_estado", "oa_objid", "oa_id",
    "oa_nombre", "oa_geoms", "inc_mapa",
    "met_pto", "prec_pto"
]

co_review = [
    field for field in co_review
    if field in co.columns
]

co[co_review].to_csv(
    OUT / "25_cochilco_enmc_revision.csv",
    index=False,
    encoding="utf-8-sig"
)

print("\nAUDITORIA 25 FINALIZADA")
print("Resultados:", OUT)
