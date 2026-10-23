from pathlib import Path
import geopandas as gpd
import pandas as pd
import shapely
from shapely.validation import explain_validity

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/processed/concesiones_6933.gpkg"
TABLES = ROOT / "outputs/tables"
PROCESSED = ROOT / "data/processed"

print("=== DIAGNOSTICO GEOMETRIAS PENDIENTES ===", flush=True)

gdf = gpd.read_file(SOURCE, engine="pyogrio")

invalid = gdf.loc[
    ~gdf.geometry.is_valid
].copy()

print("Registros totales:", len(gdf))
print("Geometrias invalidas:", len(invalid))

records = []
repaired = []

for _, row in invalid.iterrows():

    original = row.geometry
    reason = explain_validity(original)

    print("\n" + "=" * 60)
    print("ID:", row["ID_CONCESION"])
    print("Tipo:", row["TIPO_CONCESION"])
    print("Situacion:", row["SITUACION_CONCESION"])
    print("Problema:", reason)

    old_area = original.area / 10000

    candidates = [
        ("make_valid", lambda: shapely.make_valid(original)),
        ("buffer_0", lambda: original.buffer(0)),
        ("precision_001", lambda: shapely.set_precision(
            original, grid_size=0.01, mode="valid_output"
        )),
        ("precision_01", lambda: shapely.set_precision(
            original, grid_size=0.1, mode="valid_output"
        ))
    ]

    selected = None
    method = "SIN_REPARACION"

    for method_name, operation in candidates:
        try:
            candidate = operation()

            if candidate.geom_type == "GeometryCollection":
                parts = [
                    p for p in shapely.get_parts(candidate)
                    if p.geom_type in ("Polygon", "MultiPolygon")
                ]
                candidate = (
                    shapely.union_all(parts)
                    if parts else None
                )

            if candidate is None or candidate.is_empty:
                continue

            if not candidate.is_valid:
                continue

            if candidate.geom_type not in ("Polygon", "MultiPolygon"):
                continue

            new_area = candidate.area / 10000
            delta = abs(new_area - old_area)

            if delta > max(0.01, old_area * 0.001):
                continue

            selected = candidate
            method = method_name
            break

        except Exception as exc:
            print(method_name, "ERROR:", exc)

    print("Metodo seleccionado:", method)

    records.append({
        "ID_CONCESION": row["ID_CONCESION"],
        "OBJECTID": row["OBJECTID"],
        "problema": reason,
        "metodo": method,
        "area_original_ha": old_area,
        "area_reparada_ha": (
            selected.area / 10000
            if selected is not None else None
        ),
        "reparacion_exitosa": selected is not None
    })

    if selected is not None:
        item = row.copy()
        item["geometry"] = selected
        repaired.append(item)

pd.DataFrame(records).to_csv(
    TABLES / "concesiones_geometrias_pendientes.csv",
    index=False,
    encoding="utf-8-sig"
)

if repaired:
    fixes = gpd.GeoDataFrame(
        repaired,
        geometry="geometry",
        crs=gdf.crs
    )

    fixes.to_file(
        PROCESSED / "concesiones_reparaciones.gpkg",
        layer="reparaciones",
        driver="GPKG",
        engine="pyogrio"
    )

print("\n=== RESUMEN ===")
print("Invalidas detectadas:", len(invalid))
print("Reparaciones exitosas:", len(repaired))
print("Sin reparacion:", len(invalid) - len(repaired))
print("\nPROCESO FINALIZADO")
