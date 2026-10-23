from pathlib import Path
import time
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data/processed"
OUT = ROOT / "outputs/tables"
OUT.mkdir(parents=True, exist_ok=True)

REGION = "02"
OUTPUT = OUT / "concesiones_piloto_antofagasta.csv"

def clean_polygon(geom):
    if geom is None or geom.is_empty:
        return shapely.GeometryCollection()
    if not shapely.is_valid(geom):
        geom = shapely.make_valid(geom)
    parts = [
        p for p in shapely.get_parts(geom)
        if p.geom_type in ("Polygon", "MultiPolygon")
        and not p.is_empty
    ]
    return (
        shapely.union_all(parts)
        if parts else shapely.GeometryCollection()
    )

def union_geoms(geoms):
    if len(geoms) == 0:
        return shapely.GeometryCollection()
    result = shapely.union_all(geoms)
    return clean_polygon(result)

print("=== PILOTO ANTOFAGASTA ===", flush=True)

con = gpd.read_file(
    PROCESSED / "concesiones_final_6933.gpkg",
    columns=[
        "ID_CONCESION",
        "TIPO_CONCESION",
        "SITUACION_CONCESION"
    ],
    engine="pyogrio"
)

comunas = gpd.read_file(
    PROCESSED / "comunas_consolidadas.gpkg",
    engine="pyogrio"
)

comunas["codreg"] = comunas["codreg"].astype(str).str.zfill(2)
comunas = comunas.loc[comunas["codreg"] == REGION].copy()

if con.crs != comunas.crs:
    raise ValueError("CRS incompatibles")

if len(comunas) != 9:
    raise ValueError(
        f"Se esperaban 9 comunas y se encontraron {len(comunas)}"
    )

print("Concesiones cargadas:", len(con), flush=True)
print("Comunas piloto:", len(comunas), flush=True)

sindex = con.sindex
rows = []

for _, comuna in comunas.sort_values("codcom").iterrows():

    start = time.perf_counter()
    geom = comuna.geometry
    codcom = comuna["codcom"]
    nomcom = comuna["nomcom"]

    ids = sindex.query(geom, predicate="intersects")
    subset = con.iloc[ids]

    clipped = []
    tipos = []
    estados = []

    for _, feature in subset.iterrows():
        intersection = clean_polygon(
            feature.geometry.intersection(geom)
        )

        if intersection.is_empty or intersection.area <= 0:
            continue

        clipped.append(intersection)
        tipos.append(str(feature["TIPO_CONCESION"]).upper())
        estados.append(
            str(feature["SITUACION_CONCESION"]).upper()
        )

    tipos = np.array(tipos)
    estados = np.array(estados)
    clipped = np.array(clipped, dtype=object)

    def select_geoms(mask):
        return union_geoms(clipped[mask])

    constituida = estados == "CONSTITUIDA"
    tramite = estados == "EN TRAMITE"
    no_eliminada = constituida | tramite

    exploracion = select_geoms(
        constituida & (tipos == "EXPLORACION")
    )
    explotacion = select_geoms(
        constituida & (tipos == "EXPLOTACION")
    )

    total_constituida = select_geoms(constituida)
    total_tramite = select_geoms(tramite)
    total_no_eliminada = select_geoms(no_eliminada)

    overlap = exploracion.intersection(explotacion)

    area_comuna = geom.area / 10000
    ha_const = total_constituida.area / 10000
    ha_exp = exploracion.area / 10000
    ha_explot = explotacion.area / 10000
    ha_overlap = overlap.area / 10000

    error_balance = abs(
        ha_const - (ha_exp + ha_explot - ha_overlap)
    )

    if error_balance > max(0.01, ha_const * 1e-7):
        raise ValueError(
            f"Inconsistencia de areas en {nomcom}: "
            f"{error_balance:.6f} ha"
        )

    if ha_const > area_comuna + 0.01:
        raise ValueError(
            f"Cobertura supera area comunal en {nomcom}"
        )

    row = {
        "codreg": REGION,
        "codcom": codcom,
        "nomcom": nomcom,
        "superficie_comunal_ha": area_comuna,
        "n_concesiones_intersectadas": len(clipped),
        "n_constituidas": int(constituida.sum()),
        "constituida_ha": ha_const,
        "exploracion_ha": ha_exp,
        "explotacion_ha": ha_explot,
        "superposicion_ha": ha_overlap,
        "tramite_ha": total_tramite.area / 10000,
        "no_eliminada_ha": total_no_eliminada.area / 10000,
        "constituida_pct": ha_const / area_comuna * 100,
        "error_balance_ha": error_balance,
        "tiempo_seg": time.perf_counter() - start
    }

    rows.append(row)

    pd.DataFrame(rows).to_csv(
        OUTPUT,
        index=False,
        encoding="utf-8-sig"
    )

    print(
        f"{len(rows)}/{len(comunas)} "
        f"{nomcom} | "
        f"Constituida: {ha_const:,.2f} ha | "
        f"Cobertura: {row['constituida_pct']:.2f}% | "
        f"Tiempo: {row['tiempo_seg']:.1f} s",
        flush=True
    )

df = pd.DataFrame(rows)

print("\n=== RESUMEN REGIONAL PRELIMINAR ===")
print("Superficie regional:", round(df["superficie_comunal_ha"].sum(), 2))
print("Superficie constituida:", round(df["constituida_ha"].sum(), 2))
print(
    "Cobertura constituida (%):",
    round(
        df["constituida_ha"].sum() /
        df["superficie_comunal_ha"].sum() * 100, 3
    )
)
print("Tiempo total (s):", round(df["tiempo_seg"].sum(), 1))
print("Archivo:", OUTPUT)
print("\nPILOTO FINALIZADO", flush=True)
