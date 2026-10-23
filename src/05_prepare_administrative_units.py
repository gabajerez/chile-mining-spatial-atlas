from pathlib import Path
import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

SOURCE = (
    ROOT / "data" / "external" /
    "chile_comupol_2022" /
    "chile_comupol_2022.shp"
)

OUT = ROOT / "outputs" / "tables"
PROCESSED = ROOT / "data" / "processed"

OUT.mkdir(parents=True, exist_ok=True)
PROCESSED.mkdir(parents=True, exist_ok=True)

print("=" * 65)
print("PREPARACION DE UNIDADES ADMINISTRATIVAS")
print("=" * 65)

gdf = gpd.read_file(SOURCE, engine="pyogrio")

print("\n=== CONTROL ORIGINAL ===")
print("Registros:", len(gdf))
print("CRS:", gdf.crs)
print("Geometrias invalidas:", int((~gdf.geometry.is_valid).sum()))

# Identificadores como texto
for col in ["codreg", "codpro", "codcom"]:
    gdf[col] = gdf[col].astype("string").str.strip()

print("\n=== IDENTIFICADORES ===")
print("Regiones:", gdf["codreg"].nunique())
print("Provincias:", gdf["codpro"].nunique())
print("Comunas:", gdf["codcom"].nunique())
print("Codigos comunales duplicados:",
      int(gdf["codcom"].duplicated().sum()))

print("\n=== CONTROL DE CODIFICACION ===")
for value in gdf["nomreg"].dropna().unique()[:5]:
    print(repr(value))

# Transformacion a CRS equivalente
area_gdf = gdf.to_crs("EPSG:6933")

area_gdf["superficie_ha"] = (
    area_gdf.geometry.area / 10000.0
)

# Tabla comunal
comunas = area_gdf[
    ["codreg", "codpro", "codcom",
     "nomreg", "nompro", "nomcom",
     "superficie_ha"]
].copy()

comunas = comunas.sort_values(
    ["codreg", "codcom"]
)

comunas.to_csv(
    OUT / "superficie_comunal_base.csv",
    index=False,
    encoding="utf-8-sig"
)

# Tabla regional preliminar
regiones = (
    comunas.groupby(
        ["codreg", "nomreg"],
        as_index=False
    )
    .agg(
        n_comunas=("codcom", "nunique"),
        superficie_ha=("superficie_ha", "sum")
    )
)

regiones = regiones.sort_values("codreg")

regiones.to_csv(
    OUT / "superficie_regional_base.csv",
    index=False,
    encoding="utf-8-sig"
)

# Guardar capa comunal proyectada
area_gdf.to_file(
    PROCESSED / "comunas_area_6933.gpkg",
    layer="comunas",
    driver="GPKG",
    engine="pyogrio"
)

print("\n=== SUPERFICIE REGIONAL PRELIMINAR ===")
print(regiones.to_string(index=False))

print("\n=== CONTROL DE SUPERFICIES ===")
print("Superficie total (ha):",
      round(comunas["superficie_ha"].sum(), 2))

print("Comunas con superficie <= 0:",
      int((comunas["superficie_ha"] <= 0).sum()))

print("Comunas sin codigo regional:",
      int(comunas["codreg"].isna().sum()))

print("\n=== ARCHIVOS GENERADOS ===")
print("superficie_comunal_base.csv")
print("superficie_regional_base.csv")
print("comunas_area_6933.gpkg")
print("\nPROCESO FINALIZADO")
