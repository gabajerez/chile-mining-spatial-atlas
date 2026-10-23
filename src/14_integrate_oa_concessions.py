from pathlib import Path
from time import perf_counter
import pandas as pd
import geopandas as gpd
import shapely

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed"
TABLES = ROOT / "outputs/tables"

CHECKPOINT = TABLES / "integracion_oa_concesiones_checkpoint.csv"
OUT_COM = TABLES / "integracion_oa_concesiones_comunal.csv"
OUT_REG = TABLES / "integracion_oa_concesiones_regional.csv"

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

print("=== INTEGRACION ESPACIAL OA + CONCESIONES ===", flush=True)

comunas = gpd.read_file(
    DATA / "comunas_consolidadas.gpkg",
    engine="pyogrio"
)

oa = gpd.read_file(
    ROOT / "OA-2-Articulo.shp",
    engine="pyogrio"
)

con = gpd.read_file(
    DATA / "concesiones_final_6933.gpkg",
    columns=["ID_CONCESION", "SITUACION_CONCESION"],
    engine="pyogrio"
)

oa["geometry"] = oa.geometry.map(polygon_only)
oa = oa.to_crs("EPSG:6933")

con = con.loc[
    con["SITUACION_CONCESION"] == "CONSTITUIDA"
].copy()

comunas["codcom"] = comunas["codcom"].astype(str).str.zfill(5)
comunas["codreg"] = comunas["codreg"].astype(str).str.zfill(2)

if any(
    frame.crs.to_epsg() != 6933
    for frame in [comunas, oa, con]
):
    raise ValueError("CRS incompatible")

oa_tab = pd.read_csv(
    TABLES / "oa_cobertura_comunal.csv",
    dtype={"codcom": str}
)

con_tab = pd.read_csv(
    TABLES / "concesiones_cobertura_comunal.csv",
    dtype={"codcom": str}
)

oa_tab["codcom"] = oa_tab["codcom"].str.zfill(5)
con_tab["codcom"] = con_tab["codcom"].str.zfill(5)

oa_area = oa_tab.set_index("codcom")["oa_ha"]
con_area = con_tab.set_index("codcom")["constituida_ha"]

expected_codes = set(comunas["codcom"])

if set(oa_area.index) != expected_codes:
    raise ValueError("Codigos OA incompatibles")

if set(con_area.index) != expected_codes:
    raise ValueError("Codigos concesiones incompatibles")

if CHECKPOINT.exists():
    previous = pd.read_csv(
        CHECKPOINT,
        dtype={"codcom": str, "codreg": str}
    )
    previous["codcom"] = previous["codcom"].str.zfill(5)

    if previous["codcom"].duplicated().any():
        raise ValueError("Checkpoint con duplicados")

    if not set(previous["codcom"]).issubset(expected_codes):
        raise ValueError("Checkpoint con comunas desconocidas")

    rows = previous.to_dict("records")
    completed = set(previous["codcom"])
else:
    rows = []
    completed = set()

oa_index = oa.sindex
con_index = con.sindex

print("Comunas:", len(comunas), flush=True)
print("OA:", len(oa), flush=True)
print("Concesiones constituidas:", len(con), flush=True)
print("Recuperadas:", len(completed), flush=True)

for _, comuna in comunas.sort_values("codcom").iterrows():

    code = comuna["codcom"]

    if code in completed:
        continue

    t0 = perf_counter()
    geom = comuna.geometry

    # Construir union OA dentro de la comuna
    oa_candidates = oa.iloc[
        oa_index.query(geom, predicate="intersects")
    ]

    oa_parts = []

    for feature in oa_candidates.geometry:
        part = polygon_only(feature.intersection(geom))
        if not part.is_empty and part.area > 0:
            oa_parts.append(part)

    oa_union = union_geoms(oa_parts)

    # Solo necesitamos concesiones que intersectan OA.
    # La superficie total de concesiones ya esta calculada.
    overlap_ha = 0.0

    if not oa_union.is_empty:

        con_candidates = con.iloc[
            con_index.query(
                oa_union,
                predicate="intersects"
            )
        ]

        overlap_parts = []

        for feature in con_candidates.geometry:
            part = polygon_only(
                feature.intersection(oa_union)
            )

            if not part.is_empty and part.area > 0:
                overlap_parts.append(part)

        overlap_geom = union_geoms(overlap_parts)
        overlap_ha = overlap_geom.area / 10000

    oa_ha = float(oa_area.loc[code])
    con_ha = float(con_area.loc[code])

    # Control entre calculo OA original y reconstruido
    oa_reconstructed = oa_union.area / 10000
    oa_error = abs(oa_reconstructed - oa_ha)

    if oa_error > max(0.05, oa_ha * 1e-6):
        raise ValueError(
            f"Diferencia OA en {code}: {oa_error:.6f} ha"
        )

    if overlap_ha > min(oa_ha, con_ha) + 0.05:
        raise ValueError(
            f"Interseccion mayor que fuentes en {code}"
        )

    oa_solo = oa_ha - overlap_ha
    con_solo = con_ha - overlap_ha
    union_total = oa_ha + con_ha - overlap_ha
    superficie_comunal = geom.area / 10000

    if union_total > superficie_comunal + 0.05:
        raise ValueError(
            f"Union supera superficie comunal: {code}"
        )

    if min(oa_solo, con_solo, overlap_ha) < -0.05:
        raise ValueError(
            f"Superficie negativa en {code}"
        )

    row = {
        "codreg": comuna["codreg"],
        "codcom": code,
        "nomreg": comuna["nomreg"],
        "nomcom": comuna["nomcom"],
        "superficie_comunal_ha": superficie_comunal,
        "oa_ha": oa_ha,
        "concesiones_constituidas_ha": con_ha,
        "oa_concesiones_overlap_ha": overlap_ha,
        "oa_solo_ha": oa_solo,
        "concesiones_solo_ha": con_solo,
        "union_total_ha": union_total,
        "union_total_pct": (
            union_total / superficie_comunal * 100
        ),
        "oa_en_concesiones_pct": (
            overlap_ha / oa_ha * 100 if oa_ha > 0 else 0
        ),
        "oa_control_error_ha": oa_error,
        "tiempo_seg": perf_counter() - t0
    }

    rows.append(row)
    completed.add(code)

    temp = CHECKPOINT.with_suffix(".tmp")

    pd.DataFrame(rows).to_csv(
        temp,
        index=False,
        encoding="utf-8-sig"
    )
    temp.replace(CHECKPOINT)

    print(
        f"{len(rows):3d}/343 "
        f"{code} {comuna['nomcom']} | "
        f"OA: {oa_ha:,.1f} ha | "
        f"Overlap: {overlap_ha:,.1f} ha | "
        f"Union: {union_total:,.1f} ha",
        flush=True
    )

df = pd.DataFrame(rows).sort_values("codcom")

if len(df) != 343 or df["codcom"].nunique() != 343:
    raise ValueError("Procesamiento comunal incompleto")

df.to_csv(
    OUT_COM, index=False, encoding="utf-8-sig"
)

sum_cols = [
    "superficie_comunal_ha",
    "oa_ha",
    "concesiones_constituidas_ha",
    "oa_concesiones_overlap_ha",
    "oa_solo_ha",
    "concesiones_solo_ha",
    "union_total_ha"
]

regional = (
    df.groupby(["codreg", "nomreg"], as_index=False)
    [sum_cols].sum()
)

regional["union_total_pct"] = (
    regional["union_total_ha"] /
    regional["superficie_comunal_ha"] * 100
)

regional["oa_en_concesiones_pct"] = (
    regional["oa_concesiones_overlap_ha"] /
    regional["oa_ha"].where(regional["oa_ha"] > 0)
    * 100
)

regional.to_csv(
    OUT_REG, index=False, encoding="utf-8-sig"
)

print("\n=== RESULTADOS NACIONALES ===")
for col in sum_cols:
    print(col, round(df[col].sum(), 2))

print("\nCobertura integrada (%):", round(
    df["union_total_ha"].sum() /
    df["superficie_comunal_ha"].sum() * 100, 3
))

print("\n=== TOP REGIONES ===")
print(
    regional.sort_values(
        "union_total_pct", ascending=False
    )[
        ["nomreg", "union_total_ha",
         "union_total_pct",
         "oa_concesiones_overlap_ha"]
    ].to_string(index=False)
)

print("\nINTEGRACION FINALIZADA", flush=True)
