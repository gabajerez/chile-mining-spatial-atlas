from pathlib import Path
import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data/processed"
TABLES = ROOT / "outputs/tables"

comunas = gpd.read_file(
    PROCESSED / "comunas_consolidadas.gpkg",
    engine="pyogrio"
)

regiones = gpd.read_file(
    PROCESSED / "regiones_consolidadas.gpkg",
    engine="pyogrio"
)

con = pd.read_csv(
    TABLES / "concesiones_cobertura_comunal.csv",
    dtype={"codreg": str, "codcom": str}
)

oa = pd.read_csv(
    TABLES / "oa_cobertura_comunal.csv",
    dtype={"codreg": str, "codcom": str}
)

print("=== AUDITORIA DE INTEGRIDAD TERRITORIAL ===")

if comunas.crs.to_epsg() != 6933:
    raise ValueError("CRS administrativo inesperado")

# Verificar codigos administrativos
for frame in [comunas, regiones]:
    frame["codreg"] = frame["codreg"].astype(str).str.zfill(2)

comunas["codcom"] = comunas["codcom"].astype(str).str.zfill(5)

if comunas["codcom"].duplicated().any():
    raise ValueError("Codigos comunales duplicados")

if len(comunas) != 343 or len(regiones) != 16:
    raise ValueError("Cantidad administrativa inesperada")

# Buscar pares de comunas con solapamientos
sindex = comunas.sindex
overlaps = []

for i, geom in enumerate(comunas.geometry):
    candidates = sindex.query(geom, predicate="intersects")

    for j in candidates:
        if j <= i:
            continue

        other = comunas.geometry.iloc[j]
        intersection = geom.intersection(other)
        overlap_ha = intersection.area / 10000

        if overlap_ha > 0.001:
            overlaps.append({
                "codcom_1": comunas.iloc[i]["codcom"],
                "codcom_2": comunas.iloc[j]["codcom"],
                "comuna_1": comunas.iloc[i]["nomcom"],
                "comuna_2": comunas.iloc[j]["nomcom"],
                "overlap_ha": overlap_ha
            })

df_overlap = pd.DataFrame(
    overlaps,
    columns=[
        "codcom_1", "codcom_2",
        "comuna_1", "comuna_2", "overlap_ha"
    ]
)

df_overlap.to_csv(
    TABLES / "control_solapamiento_comunas.csv",
    index=False,
    encoding="utf-8-sig"
)

print("Pares con solapamiento > 0.001 ha:", len(df_overlap))
print("Suma de areas de pares (ha):",
      round(df_overlap["overlap_ha"].sum(), 4))

if not df_overlap.empty:
    print(
        df_overlap.nlargest(10, "overlap_ha")
        .to_string(index=False)
    )

# Integridad de cobertura
for name, df, area_col in [
    ("CONCESIONES", con, "constituida_ha"),
    ("OA", oa, "oa_ha")
]:
    print(f"\n=== {name} ===")

    print("Registros:", len(df))
    print("Codigos unicos:", df["codcom"].nunique())
    print("Superficie total (ha):",
          round(df[area_col].sum(), 2))
    print("Superficies negativas:",
          int((df[area_col] < -0.001).sum()))

    missing = set(comunas["codcom"]) - set(df["codcom"])
    extra = set(df["codcom"]) - set(comunas["codcom"])

    print("Codigos faltantes:", len(missing))
    print("Codigos adicionales:", len(extra))

    if missing or extra:
        raise ValueError(
            f"Inconsistencia de codigos en {name}"
        )

# Comparacion regional de superficies
regional_sum = (
    comunas.assign(area_ha=comunas.geometry.area / 10000)
    .groupby("codreg")["area_ha"]
    .sum()
)

regional_geom = regiones.set_index("codreg").geometry.area / 10000
differences = (regional_sum - regional_geom).abs()

print("\n=== CONTROL REGIONAL ===")
print("Maxima diferencia regional (ha):",
      round(differences.max(), 6))
print("Suma superficies comunales (ha):",
      round(regional_sum.sum(), 2))
print("Suma superficies regionales (ha):",
      round(regional_geom.sum(), 2))

print("\nAUDITORIA FINALIZADA")
