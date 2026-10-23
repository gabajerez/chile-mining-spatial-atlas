from pathlib import Path
from time import perf_counter
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data/processed"
OUT = ROOT / "outputs/tables"
OUT.mkdir(parents=True, exist_ok=True)

CHECKPOINT = OUT / "concesiones_nacional_checkpoint.csv"
COMUNAL = OUT / "concesiones_cobertura_comunal.csv"
REGIONAL = OUT / "concesiones_cobertura_regional.csv"

def polygon_only(geom):
    if geom is None or geom.is_empty:
        return shapely.GeometryCollection()

    if not geom.is_valid:
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
    if not geoms:
        return shapely.GeometryCollection()
    return polygon_only(shapely.union_all(geoms))

print("=== COBERTURA NACIONAL DE CONCESIONES ===", flush=True)

con = gpd.read_file(
    PROCESSED / "concesiones_final_6933.gpkg",
    columns=["ID_CONCESION", "TIPO_CONCESION",
             "SITUACION_CONCESION"],
    engine="pyogrio"
)

comunas = gpd.read_file(
    PROCESSED / "comunas_consolidadas.gpkg",
    engine="pyogrio"
)

if con.crs != comunas.crs or con.crs.to_epsg() != 6933:
    raise ValueError("CRS incompatible")

comunas["codcom"] = comunas["codcom"].astype(str).str.zfill(5)
comunas["codreg"] = comunas["codreg"].astype(str).str.zfill(2)

if len(con) != 104147 or len(comunas) != 343:
    raise ValueError("Cantidad inesperada de registros")

if con["ID_CONCESION"].duplicated().any():
    raise ValueError("ID_CONCESION no es único")

if comunas["codcom"].duplicated().any():
    raise ValueError("Código comunal duplicado")

# Reanudar solamente cuando existe un checkpoint previo
if CHECKPOINT.exists():
    previous = pd.read_csv(
        CHECKPOINT,
        dtype={"codcom": str, "codreg": str}
    )
    rows = previous.to_dict("records")
    completed = set(previous["codcom"].str.zfill(5))
    print("Comunas recuperadas:", len(completed), flush=True)
else:
    rows = []
    completed = set()

if len(completed) != len(rows):
    raise ValueError("Checkpoint con códigos duplicados")

sindex = con.sindex

print("Concesiones:", len(con), flush=True)
print("Comunas:", len(comunas), flush=True)

start_total = perf_counter()

for _, comuna in comunas.sort_values("codcom").iterrows():

    code = comuna["codcom"]

    if code in completed:
        continue

    start = perf_counter()
    geom = comuna.geometry

    candidates = sindex.query(
        geom, predicate="intersects"
    )

    sub = con.iloc[candidates]

    groups = {
        "exploracion": [],
        "explotacion": [],
        "constituida": [],
        "tramite": []
    }

    n_const = 0
    n_intersect = 0

    for feature in sub.itertuples():
        part = polygon_only(
            feature.geometry.intersection(geom)
        )

        if part.is_empty or part.area <= 0:
            continue

        n_intersect += 1
        estado = str(feature.SITUACION_CONCESION).upper()
        tipo = str(feature.TIPO_CONCESION).upper()

        if estado == "CONSTITUIDA":
            n_const += 1
            groups["constituida"].append(part)

            if tipo == "EXPLORACION":
                groups["exploracion"].append(part)
            elif tipo == "EXPLOTACION":
                groups["explotacion"].append(part)

        elif estado == "EN TRAMITE":
            groups["tramite"].append(part)

    exp = union_geoms(groups["exploracion"])
    explot = union_geoms(groups["explotacion"])
    constituida = union_geoms(groups["constituida"])
    tramite = union_geoms(groups["tramite"])

    no_eliminada = union_geoms(
        [constituida, tramite]
    )

    overlap = exp.intersection(explot)

    area_com = geom.area / 10000
    area_const = constituida.area / 10000
    area_exp = exp.area / 10000
    area_explot = explot.area / 10000
    area_overlap = overlap.area / 10000

    error = abs(
        area_const -
        (area_exp + area_explot - area_overlap)
    )

    if error > max(0.01, area_const * 1e-7):
        raise ValueError(
            f"Error de balance en {code}: {error}"
        )

    if area_const > area_com + 0.01:
        raise ValueError(
            f"Cobertura superior al 100%: {code}"
        )

    row = {
        "codreg": comuna["codreg"],
        "codcom": code,
        "nomreg": comuna["nomreg"],
        "nomcom": comuna["nomcom"],
        "superficie_comunal_ha": area_com,
        "n_concesiones_intersectadas": n_intersect,
        "n_constituidas": n_const,
        "constituida_ha": area_const,
        "exploracion_ha": area_exp,
        "explotacion_ha": area_explot,
        "superposicion_ha": area_overlap,
        "tramite_ha": tramite.area / 10000,
        "no_eliminada_ha": no_eliminada.area / 10000,
        "constituida_pct": area_const / area_com * 100,
        "no_eliminada_pct":
            no_eliminada.area / geom.area * 100,
        "error_balance_ha": error,
        "tiempo_seg": perf_counter() - start
    }

    rows.append(row)
    completed.add(code)

    # Guardado incremental y seguro
    temp = CHECKPOINT.with_suffix(".tmp")
    pd.DataFrame(rows).to_csv(
        temp, index=False, encoding="utf-8-sig"
    )
    temp.replace(CHECKPOINT)

    print(
        f"{len(rows):3d}/{len(comunas)} "
        f"{code} {comuna['nomcom']} | "
        f"{area_const:,.1f} ha | "
        f"{row['constituida_pct']:.2f}% | "
        f"{row['tiempo_seg']:.1f} s",
        flush=True
    )

df = pd.DataFrame(rows).sort_values("codcom")

if len(df) != 343:
    raise ValueError(
        f"Procesamiento incompleto: {len(df)}/343"
    )

df.to_csv(
    COMUNAL, index=False, encoding="utf-8-sig"
)

# Agregación de hectáreas comunales por región
# Los conteos de concesiones NO se suman como valores únicos
reg = (
    df.groupby(["codreg", "nomreg"], as_index=False)
    .agg(
        n_comunas=("codcom", "nunique"),
        superficie_regional_ha=("superficie_comunal_ha", "sum"),
        constituida_ha=("constituida_ha", "sum"),
        exploracion_ha=("exploracion_ha", "sum"),
        explotacion_ha=("explotacion_ha", "sum"),
        superposicion_ha=("superposicion_ha", "sum"),
        tramite_ha=("tramite_ha", "sum"),
        no_eliminada_ha=("no_eliminada_ha", "sum")
    )
)

reg["constituida_pct"] = (
    reg["constituida_ha"] /
    reg["superficie_regional_ha"] * 100
)

reg["no_eliminada_pct"] = (
    reg["no_eliminada_ha"] /
    reg["superficie_regional_ha"] * 100
)

if len(reg) != 16:
    raise ValueError("Se esperaban 16 regiones")

reg.to_csv(
    REGIONAL, index=False, encoding="utf-8-sig"
)

print("\n=== RESULTADOS NACIONALES ===")
print("Comunas:", len(df))
print("Regiones:", len(reg))
print("Superficie constituida (ha):",
      round(df["constituida_ha"].sum(), 2))
print("Cobertura constituida (%):",
      round(
          df["constituida_ha"].sum() /
          df["superficie_comunal_ha"].sum() * 100, 3
      ))

print("\n=== TOP REGIONAL ===")
print(
    reg.sort_values("constituida_pct", ascending=False)
    [["nomreg", "constituida_ha", "constituida_pct"]]
    .to_string(index=False)
)

print("\n=== CONTROL ===")
print("Comunas con cobertura > 100%:",
      int((df["constituida_pct"] > 100.000001).sum()))
print("Máximo error de balance (ha):",
      df["error_balance_ha"].max())
print("Tiempo de esta ejecución (s):",
      round(perf_counter() - start_total, 1))

print("\nPROCESO NACIONAL FINALIZADO", flush=True)
