from pathlib import Path
import geopandas as gpd
import pandas as pd
import shapely

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/processed/enmc"
SENS = BASE / "sensibilidad"
OUT = ROOT / "reports/enmc"

CRS = "EPSG:6933"

def read_shapes(path):
    if not path.exists():
        raise FileNotFoundError(path)
    gdf = gpd.read_file(path, engine="pyogrio")
    if gdf.crs is None:
        raise ValueError(f"Sin CRS: {path}")
    return gdf.to_crs(CRS)

def polygonal(geom):
    if geom is None or geom.is_empty:
        return shapely.GeometryCollection()
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
    parts = [
        p for p in shapely.get_parts(geom)
        if p.geom_type in ("Polygon", "MultiPolygon")
        and not p.is_empty
    ]
    return shapely.union_all(parts) if parts else shapely.GeometryCollection()

def union_layer(path):
    df = read_shapes(path)
    parts = [
        polygonal(g) for g in df.geometry
        if g is not None and not g.is_empty
    ]
    return polygonal(shapely.union_all(parts))

print("=== PASO 42: COMPONENTE CONJUNTO ===", flush=True)

sites = union_layer(SENS / "39_sitios_prioritarios.gpkg")
bios = union_layer(SENS / "39_reservas_biosfera.gpkg")

C = union_layer(
    BASE / "35_concesiones_constituidas_ambito.gpkg"
)
L = union_layer(
    BASE / "35_concesion_residual_ambito.gpkg"
)

print("Uniendo sitios prioritarios y reservas...", flush=True)
S = polygonal(shapely.union_all([sites, bios]))

area = S.area / 10000.0
con = S.intersection(C).area / 10000.0
res = S.intersection(L).area / 10000.0

if area <= 0 or con > area + 0.01 or res > con + 0.01:
    raise RuntimeError("Inconsistencia de superficies")

result = pd.DataFrame([{
    "componente": "sitios_prioritarios_reservas_biosfera",
    "superficie_sensible_unica_ha": area,
    "superficie_sensible_concesionada_ha": con,
    "porcentaje_sensible_concesionada": con / area * 100,
    "superficie_sensible_residual_provisional_ha": res,
    "porcentaje_sensible_residual_provisional": res / area * 100,
    "peso_ist": 0.099,
    "estado": "PROVISIONAL"
}])

dest = OUT / "42_overlap_biodiversidad_conjunta.csv"
result.to_csv(dest, index=False, encoding="utf-8-sig")

print(result.to_string(index=False))
print("Archivo:", dest)
print("PASO 42 FINALIZADO", flush=True)
