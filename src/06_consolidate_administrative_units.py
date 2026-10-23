from pathlib import Path
import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/processed/comunas_area_6933.gpkg"
OUT = ROOT / "data/processed"
TABLES = ROOT / "outputs/tables"

OUT.mkdir(parents=True, exist_ok=True)
TABLES.mkdir(parents=True, exist_ok=True)

print("=== CONSOLIDACION ADMINISTRATIVA ===")

gdf = gpd.read_file(SOURCE, engine="pyogrio")

assert gdf.crs.to_epsg() == 6933, "CRS inesperado"

for col in ["codreg", "codpro", "codcom"]:
    gdf[col] = gdf[col].astype("string").str.strip()

print("Geometrias originales:", len(gdf))
print("Codigos comunales:", gdf["codcom"].nunique())

# Verificar que cada codigo comunal tenga atributos coherentes
for field in ["codreg", "codpro", "nomreg", "nompro", "nomcom"]:
    inconsistencias = (
        gdf.groupby("codcom")[field].nunique(dropna=False) > 1
    )
    if inconsistencias.any():
        raise ValueError(
            f"Atributos inconsistentes en {field}: "
            f"{inconsistencias[inconsistencias].index.tolist()}"
        )

# Disolver fragmentos del mismo territorio comunal
comunas = gdf.dissolve(
    by="codcom",
    as_index=False,
    aggfunc="first",
    method="unary"
)

comunas["superficie_ha"] = comunas.geometry.area / 10000

# Disolver comunas para generar regiones
regiones = comunas.dissolve(
    by="codreg",
    as_index=False,
    aggfunc="first",
    method="unary"
)

regiones["superficie_ha"] = regiones.geometry.area / 10000

n_comunas = (
    comunas.groupby("codreg")["codcom"]
    .nunique()
    .rename("n_comunas")
    .reset_index()
)

regiones = regiones.merge(n_comunas, on="codreg", how="left")

# Comparacion entre suma de fragmentos y union espacial
original = (
    gdf.groupby("codcom")["superficie_ha"]
    .sum()
    .rename("ha_fragmentos")
    .reset_index()
)

control = comunas[["codcom", "nomcom", "superficie_ha"]].merge(
    original,
    on="codcom",
    how="left"
)

control["diferencia_ha"] = (
    control["ha_fragmentos"] - control["superficie_ha"]
)

print("\n=== CONTROL DE CONSOLIDACION ===")
print("Comunas:", len(comunas))
print("Regiones:", len(regiones))
print("Geometrias comunales invalidas:",
      int((~comunas.geometry.is_valid).sum()))
print("Geometrias regionales invalidas:",
      int((~regiones.geometry.is_valid).sum()))

print("\n=== FRAGMENTOS DE QUEILEN ===")
print(
    control.loc[control["codcom"] == "10207"]
    .to_string(index=False)
)

print("\n=== MAYORES DIFERENCIAS DE SUPERFICIE ===")
print(
    control.reindex(
        control["diferencia_ha"].abs()
        .sort_values(ascending=False).index
    ).head(10).to_string(index=False)
)

# Exportacion de geometria administrativa consolidada
comunas.to_file(
    OUT / "comunas_consolidadas.gpkg",
    layer="comunas",
    driver="GPKG",
    engine="pyogrio"
)

regiones.to_file(
    OUT / "regiones_consolidadas.gpkg",
    layer="regiones",
    driver="GPKG",
    engine="pyogrio"
)

# Tablas estadisticas
comunas.drop(columns="geometry").to_csv(
    TABLES / "superficie_comunal_final.csv",
    index=False,
    encoding="utf-8-sig"
)

regiones.drop(columns="geometry").to_csv(
    TABLES / "superficie_regional_final.csv",
    index=False,
    encoding="utf-8-sig"
)

control.to_csv(
    TABLES / "control_disolucion_comunal.csv",
    index=False,
    encoding="utf-8-sig"
)

print("\n=== SUPERFICIE REGIONAL ===")
print(
    regiones[[
        "codreg", "nomreg", "n_comunas", "superficie_ha"
    ]].sort_values("codreg").to_string(index=False)
)

print("\n=== RESUMEN ===")
print("Superficie comunal total (ha):",
      round(comunas["superficie_ha"].sum(), 2))
print("Superficie regional total (ha):",
      round(regiones["superficie_ha"].sum(), 2))

print("\nPROCESO FINALIZADO")
