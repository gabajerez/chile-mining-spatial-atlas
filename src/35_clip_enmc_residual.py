from pathlib import Path
import pandas as pd
import geopandas as gpd
import shapely

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data/processed/enmc"
REPORT = ROOT / "reports/enmc"
CRS = "EPSG:6933"

PROC.mkdir(parents=True, exist_ok=True)
REPORT.mkdir(parents=True, exist_ok=True)

CON_PATH = PROC / "32_union_concesiones_constituidas.gpkg"
RES_PATH = PROC / "32_concesion_residual_provisional.gpkg"
COM_PATH = ROOT / "data/processed/comunas_consolidadas.gpkg"

def polygonal(geom):
    if geom is None or geom.is_empty:
        return shapely.GeometryCollection()

    if not geom.is_valid:
        geom = shapely.make_valid(geom)

    parts = [
        g for g in shapely.get_parts(geom)
        if g.geom_type in ("Polygon", "MultiPolygon")
        and not g.is_empty
    ]

    return shapely.union_all(parts) if parts else shapely.GeometryCollection()

def hectares(geom):
    return geom.area / 10000.0

def read_union(path):
    gdf = gpd.read_file(path, engine="pyogrio")
    if gdf.crs is None:
        raise ValueError(f"Sin CRS: {path}")
    gdf = gdf.to_crs(CRS)
    return polygonal(shapely.union_all(gdf.geometry.to_numpy()))

def save_geom(geom, name, label):
    if geom.is_empty:
        raise ValueError(f"Geometria vacia: {name}")

    path = PROC / name
    if path.exists():
        path.unlink()

    gpd.GeoDataFrame(
        {"estado": [label]},
        geometry=[geom],
        crs=CRS
    ).to_file(
        path, layer="cobertura",
        driver="GPKG", engine="pyogrio"
    )

    print("Guardado:", path, flush=True)

print("=== PASO 35: COBERTURA EN AMBITO COMUNAL ===", flush=True)

print("Leyendo uniones existentes...", flush=True)
C = read_union(CON_PATH)
R = read_union(RES_PATH)

print("Leyendo limites comunales...", flush=True)
comunas = gpd.read_file(COM_PATH, engine="pyogrio").to_crs(CRS)

if len(comunas) != 343:
    raise ValueError(f"Se esperaban 343 comunas: {len(comunas)}")

T = polygonal(shapely.union_all(
    [polygonal(g) for g in comunas.geometry]
))

print("Recortando cobertura concesional...", flush=True)
C_clip = polygonal(C.intersection(T))

print("Recortando superficie residual...", flush=True)
R_clip = polygonal(R.intersection(T))

print("Calculando superficie descontada...", flush=True)
D_clip = polygonal(C_clip.difference(R_clip))

area_con = hectares(C_clip)
area_res = hectares(R_clip)
area_des = hectares(D_clip)

error = area_con - area_res - area_des
fuera = hectares(R_clip.difference(C_clip))

if abs(error) > 0.01:
    raise RuntimeError(f"Balance inconsistente: {error} ha")

if fuera > 0.01:
    raise RuntimeError(
        f"Residual fuera de concesiones: {fuera} ha"
    )

expected = 16239453.837011896
if abs(area_con - expected) > 1:
    raise RuntimeError(
        "La cobertura no coincide con el paso 34"
    )

print("Guardando capas...", flush=True)

save_geom(
    C_clip,
    "35_concesiones_constituidas_ambito.gpkg",
    "CONCESION_CONSTITUIDA"
)

save_geom(
    R_clip,
    "35_concesion_residual_ambito.gpkg",
    "RESIDUAL_PROVISIONAL"
)

save_geom(
    D_clip,
    "35_superficie_descontada_oa_ambito.gpkg",
    "DESCONTADA_OA_CANDIDATA"
)

summary = pd.DataFrame([{
    "concesion_constituida_ha": area_con,
    "residual_provisional_ha": area_res,
    "descontado_oa_ha": area_des,
    "residual_pct": 100 * area_res / area_con,
    "error_balance_ha": error,
    "residual_fuera_concesiones_ha": fuera,
    "estado_validacion": "PROVISIONAL",
    "cochilco_poligonos_descontados": False,
    "oa_operacion_confirmada": False
}])

dest = REPORT / "35_residual_ambito_resumen.csv"
summary.to_csv(dest, index=False, encoding="utf-8-sig")

print("\n=== RESUMEN ===")
print(summary.to_string(index=False))
print("\nArchivo:", dest)
print("PASO 35 FINALIZADO", flush=True)
