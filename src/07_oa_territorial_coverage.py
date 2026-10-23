from pathlib import Path
import re
import unicodedata
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
from shapely import make_valid, union_all
from shapely.geometry import GeometryCollection

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "tables"
PROCESSED = ROOT / "data" / "processed"

OUT.mkdir(parents=True, exist_ok=True)
PROCESSED.mkdir(parents=True, exist_ok=True)

def norm(value):
    if pd.isna(value):
        return ""
    s = unicodedata.normalize("NFKD", str(value).upper().strip())
    return "".join(c for c in s if not unicodedata.combining(c))

def copper_class(value):
    s = norm(value)
    if s == "COBRE":
        return "cobre_exclusivo"
    if re.search(r"\bCOBRE\b", s):
        return "cobre_asociado"
    return "sin_cobre"

def polygon_only(geom):
    if geom is None or geom.is_empty:
        return GeometryCollection()

    if not geom.is_valid:
        geom = make_valid(geom)

    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom

    if hasattr(geom, "geoms"):
        polygons = [
            g for g in geom.geoms
            if g.geom_type in ("Polygon", "MultiPolygon")
            and not g.is_empty
        ]
        if polygons:
            return union_all(polygons)

    return GeometryCollection()

print("=== CARGANDO CAPAS ===", flush=True)

oa = gpd.read_file(
    ROOT / "OA-2-Articulo.shp",
    engine="pyogrio"
)

comunas = gpd.read_file(
    PROCESSED / "comunas_consolidadas.gpkg",
    engine="pyogrio"
)

print("OA:", len(oa), flush=True)
print("Comunas:", len(comunas), flush=True)

if oa.crs is None or comunas.crs is None:
    raise ValueError("Una capa no tiene CRS definido")

print("\n=== PREPARANDO OA ===", flush=True)

oa["clase_cobre"] = oa["MINERAL"].map(copper_class)

invalid_before = int((~oa.geometry.is_valid).sum())
print("Invalidas originales:", invalid_before, flush=True)

oa["geometry"] = oa.geometry.map(polygon_only)

oa = oa.loc[
    oa.geometry.notna() & ~oa.geometry.is_empty
].copy()

oa = oa.to_crs("EPSG:6933")
comunas = comunas.to_crs("EPSG:6933")

oa["area_original_ha"] = oa.geometry.area / 10000

print("Geometrias procesables:", len(oa), flush=True)
print(
    "Invalidas restantes:",
    int((~oa.geometry.is_valid).sum()),
    flush=True
)

print("\n=== INTERSECCION COMUNAL ===", flush=True)

sindex = oa.sindex

rows = []
classes = [
    "cobre_exclusivo",
    "cobre_asociado",
    "sin_cobre"
]

for i, comuna in comunas.iterrows():

    geom = comuna.geometry
    candidates = sindex.query(geom, predicate="intersects")
    subset = oa.iloc[candidates]

    intersected = []

    for _, feature in subset.iterrows():
        part = polygon_only(
            feature.geometry.intersection(geom)
        )

        if not part.is_empty:
            intersected.append((
                feature["clase_cobre"],
                part
            ))

    all_geoms = [g for _, g in intersected]

    total_geom = (
        union_all(all_geoms)
        if all_geoms else GeometryCollection()
    )

    class_geoms = {}

    for cls in classes:
        geoms = [g for c, g in intersected if c == cls]
        class_geoms[cls] = (
            union_all(geoms)
            if geoms else GeometryCollection()
        )

    cobre_geom = union_all([
        class_geoms["cobre_exclusivo"],
        class_geoms["cobre_asociado"]
    ])

    area_comuna = geom.area / 10000
    area_total = total_geom.area / 10000
    area_cobre = cobre_geom.area / 10000

    row = {
        "codreg": comuna["codreg"],
        "codcom": comuna["codcom"],
        "nomreg": comuna["nomreg"],
        "nomcom": comuna["nomcom"],
        "superficie_comunal_ha": area_comuna,
        "oa_ha": area_total,
        "cobre_exclusivo_ha":
            class_geoms["cobre_exclusivo"].area / 10000,
        "cobre_asociado_ha":
            class_geoms["cobre_asociado"].area / 10000,
        "sin_cobre_ha":
            class_geoms["sin_cobre"].area / 10000,
        "cobre_total_ha": area_cobre,
        "oa_pct": (
            area_total / area_comuna * 100
            if area_comuna > 0 else np.nan
        ),
        "cobre_pct": (
            area_cobre / area_comuna * 100
            if area_comuna > 0 else np.nan
        )
    }

    rows.append(row)

    if len(rows) % 25 == 0:
        print(
            f"Procesadas {len(rows)}/{len(comunas)} comunas",
            flush=True
        )

df = pd.DataFrame(rows)
df = df.sort_values(["codreg", "codcom"])

df.to_csv(
    OUT / "oa_cobertura_comunal.csv",
    index=False,
    encoding="utf-8-sig"
)

print("\n=== AGREGACION REGIONAL ===", flush=True)

regiones = (
    df.groupby(["codreg", "nomreg"], as_index=False)
    .agg(
        superficie_regional_ha=("superficie_comunal_ha", "sum"),
        oa_ha=("oa_ha", "sum"),
        cobre_exclusivo_ha=("cobre_exclusivo_ha", "sum"),
        cobre_asociado_ha=("cobre_asociado_ha", "sum"),
        sin_cobre_ha=("sin_cobre_ha", "sum"),
        cobre_total_ha=("cobre_total_ha", "sum")
    )
)

regiones["oa_pct"] = (
    regiones["oa_ha"] /
    regiones["superficie_regional_ha"] * 100
)

regiones["cobre_pct"] = (
    regiones["cobre_total_ha"] /
    regiones["superficie_regional_ha"] * 100
)

regiones.to_csv(
    OUT / "oa_cobertura_regional.csv",
    index=False,
    encoding="utf-8-sig"
)

print("\n=== CONTROL FINAL ===")
print("Comunas:", len(df))
print("Regiones:", len(regiones))
print("Superficie OA comunal total (ha):",
      round(df["oa_ha"].sum(), 2))
print("Superficie cobre total (ha):",
      round(df["cobre_total_ha"].sum(), 2))

print("\n=== TOP 10 REGIONES ===")
print(
    regiones.sort_values("oa_pct", ascending=False)
    [["nomreg", "oa_ha", "oa_pct",
      "cobre_total_ha", "cobre_pct"]]
    .head(10).to_string(index=False)
)

print("\n=== CONTROLES DE COBERTURA ===")
print("Comunas con OA > 100%:",
      int((df["oa_pct"] > 100.000001).sum()))
print("Comunas con cobre > OA:",
      int((df["cobre_total_ha"] > df["oa_ha"] + 0.01).sum()))

print("\nPROCESO FINALIZADO", flush=True)
