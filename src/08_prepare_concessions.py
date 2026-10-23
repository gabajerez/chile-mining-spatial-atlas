from pathlib import Path
import gc
import numpy as np
import pandas as pd
import geopandas as gpd
import pyogrio
import shapely

ROOT = Path(__file__).resolve().parents[1]

SOURCE = ROOT / "sernageomin_concesiones_2026-06-05.geojson"
DEST = ROOT / "data/processed/concesiones_6933.gpkg"
TABLE = ROOT / "outputs/tables/concesiones_control_geometrico.csv"
SUMMARY = ROOT / "outputs/tables/concesiones_resumen_preparacion.csv"

BATCH = 5000

DEST.parent.mkdir(parents=True, exist_ok=True)
TABLE.parent.mkdir(parents=True, exist_ok=True)

print("=== PREPARACION CONCESIONES ===", flush=True)

info = pyogrio.read_info(SOURCE)
total = info["features"]

print("Registros originales:", total, flush=True)

if DEST.exists():
    DEST.unlink()

results = []
first = True

for start in range(0, total, BATCH):

    count = min(BATCH, total - start)

    gdf = gpd.read_file(
        SOURCE,
        engine="pyogrio",
        skip_features=start,
        max_features=count
    )

    if gdf.crs is None:
        raise ValueError("Fuente sin CRS")

    invalid_before = int((~gdf.geometry.is_valid).sum())

    # Reparar geometria preservando componentes poligonales
    geometries = shapely.make_valid(
        gdf.geometry.array
    )

    geometries = shapely.get_parts(geometries)

    # Volver a crear las geometrias individualmente
    repaired = []

    for geom in gdf.geometry:
        if geom is None or geom.is_empty:
            repaired.append(None)
            continue

        if not geom.is_valid:
            geom = shapely.make_valid(geom)

        parts = []

        if geom.geom_type in ("Polygon", "MultiPolygon"):
            parts = [geom]
        elif hasattr(geom, "geoms"):
            parts = [
                p for p in geom.geoms
                if p.geom_type in ("Polygon", "MultiPolygon")
            ]

        repaired.append(
            shapely.union_all(parts) if parts else None
        )

    gdf["geometry"] = repaired

    gdf = gdf.loc[
        gdf.geometry.notna() &
        ~gdf.geometry.is_empty
    ].copy()

    gdf = gdf.to_crs("EPSG:6933")

    gdf["area_geom_ha"] = gdf.geometry.area / 10000
    gdf["area_decl_ha"] = pd.to_numeric(
        gdf["HECTAREAS"], errors="coerce"
    )

    gdf["dif_area_ha"] = (
        gdf["area_geom_ha"] - gdf["area_decl_ha"]
    )

    gdf["dif_area_pct"] = np.where(
        gdf["area_decl_ha"] > 0,
        gdf["dif_area_ha"] /
        gdf["area_decl_ha"] * 100,
        np.nan
    )

    # No exportar datos personales de titulares
    keep = [
        "OBJECTID", "ID_CONCESION", "NUMERO_ROL",
        "COMUNA", "ID_COMUNA",
        "TIPO_CONCESION", "SITUACION_CONCESION",
        "HECTAREAS", "area_geom_ha",
        "area_decl_ha", "dif_area_ha",
        "dif_area_pct", "geometry"
    ]

    gdf = gdf[keep]

    pyogrio.write_dataframe(
        gdf,
        DEST,
        layer="concesiones",
        driver="GPKG",
        append=not first,
        spatial_index=True
    )

    first = False

    results.append({
        "inicio": start,
        "registros_lote": count,
        "registros_exportados": len(gdf),
        "invalidas_originales": invalid_before,
        "invalidas_finales": int(
            (~gdf.geometry.is_valid).sum()
        ),
        "ha_declaradas": float(
            gdf["area_decl_ha"].sum()
        ),
        "ha_geometricas": float(
            gdf["area_geom_ha"].sum()
        )
    })

    print(
        f"Procesados {min(start + count, total)}/{total} "
        f"| Invalidas originales lote: {invalid_before} "
        f"| Exportadas: {len(gdf)}",
        flush=True
    )

    del gdf, repaired, geometries
    gc.collect()

summary = pd.DataFrame(results)

summary.to_csv(
    SUMMARY,
    index=False,
    encoding="utf-8-sig"
)

print("\n=== CONTROL FINAL ===")
print("Lotes:", len(summary))
print("Registros exportados:",
      int(summary["registros_exportados"].sum()))
print("Invalidas originales:",
      int(summary["invalidas_originales"].sum()))
print("Invalidas restantes:",
      int(summary["invalidas_finales"].sum()))

print("Hectareas declaradas:",
      round(summary["ha_declaradas"].sum(), 2))
print("Hectareas geometricas:",
      round(summary["ha_geometricas"].sum(), 2))

# Tabla de calidad geometrica
con = gpd.read_file(
    DEST,
    engine="pyogrio",
    ignore_geometry=True
)

control = (
    con.groupby(
        ["TIPO_CONCESION", "SITUACION_CONCESION"],
        dropna=False,
        as_index=False
    )
    .agg(
        n_concesiones=("ID_CONCESION", "nunique"),
        ha_declaradas=("area_decl_ha", "sum"),
        ha_geometricas=("area_geom_ha", "sum"),
        diferencia_mediana_pct=("dif_area_pct", "median")
    )
)

control.to_csv(
    TABLE,
    index=False,
    encoding="utf-8-sig"
)

print("\n=== RESUMEN POR TIPO Y SITUACION ===")
print(control.to_string(index=False))

print("\nPROCESO FINALIZADO", flush=True)
