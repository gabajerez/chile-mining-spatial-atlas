"""Overlap de áreas protegidas por teselas disjuntas, con checkpoint.
No altera los GeoPackage existentes. Uso: python -u src/40b_overlap_areas_protegidas_tiles.py
"""
from pathlib import Path
import math
import pandas as pd
import geopandas as gpd
import shapely
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / 'data' / 'processed' / 'enmc'
SENS = PROC / 'sensibilidad'
REPORT = ROOT / 'reports' / 'enmc'
REPORT.mkdir(parents=True, exist_ok=True)
CRS = 'EPSG:6933'
CELL_M = 75_000
CHECKPOINT = REPORT / '40b_areas_protegidas_teselas.csv'
OUTPUT = REPORT / '40_overlap_areas_protegidas.csv'


def polygonal(geometry):
    if geometry is None or geometry.is_empty:
        return shapely.GeometryCollection()
    if not geometry.is_valid:
        geometry = shapely.make_valid(geometry)
    parts = [g for g in shapely.get_parts(geometry)
             if g.geom_type in ('Polygon', 'MultiPolygon') and not g.is_empty]
    return shapely.union_all(parts) if parts else shapely.GeometryCollection()


def union_file(path):
    frame = gpd.read_file(path, engine='pyogrio')
    if frame.crs is None:
        raise RuntimeError(f'CRS ausente: {path}')
    frame = frame.to_crs(CRS)
    if len(frame) != 1:
        raise RuntimeError(f'Se esperaba una sola geometría en {path}: {len(frame)}')
    return polygonal(frame.geometry.iloc[0])


files = sorted(SENS.glob('*areas_protegidas*.gpkg'))
if len(files) != 1:
    raise RuntimeError(f'Se esperaba 1 GeoPackage de áreas protegidas en {SENS}; encontrados: {files}')
source = files[0]
S = gpd.read_file(source, engine='pyogrio').to_crs(CRS)
S = S.loc[S.geometry.notna() & ~S.geometry.is_empty].copy().reset_index(drop=True)
S['geometry'] = S.geometry.map(polygonal)
S = S.loc[~S.geometry.is_empty].copy().reset_index(drop=True)
if S.empty:
    raise RuntimeError('Capa de áreas protegidas vacía')

C = union_file(PROC / '35_concesiones_constituidas_ambito.gpkg')
L = union_file(PROC / '35_concesion_residual_ambito.gpkg')
idx = S.sindex
xmin, ymin, xmax, ymax = S.total_bounds
ix0, ix1 = math.floor(xmin / CELL_M), math.ceil(xmax / CELL_M)
iy0, iy1 = math.floor(ymin / CELL_M), math.ceil(ymax / CELL_M)

saved = pd.read_csv(CHECKPOINT) if CHECKPOINT.exists() else pd.DataFrame()
completed = set(saved['tile_id'].astype(str)) if not saved.empty else set()
results = saved.to_dict('records') if not saved.empty else []
print('=== PASO 40b: AREAS PROTEGIDAS POR TESELAS ===', flush=True)
print(f'Fuente: {source}, entidades: {len(S)}, tesela: {CELL_M/1000:g} km', flush=True)
print(f'Teselas ya calculadas: {len(completed)}', flush=True)

for ix in range(ix0, ix1):
    for iy in range(iy0, iy1):
        tile_id = f'{ix}_{iy}'
        if tile_id in completed:
            continue
        tile = box(ix*CELL_M, iy*CELL_M, (ix+1)*CELL_M, (iy+1)*CELL_M)
        candidates = idx.query(tile, predicate='intersects')
        if len(candidates) == 0:
            continue
        partial = []
        for geom in S.geometry.iloc[candidates]:
            clipped = polygonal(geom.intersection(tile))
            if not clipped.is_empty:
                partial.append(clipped)
        if not partial:
            continue
        unique = polygonal(shapely.union_all(partial))
        area_s = unique.area / 10000.0
        area_c = unique.intersection(C).area / 10000.0
        area_l = unique.intersection(L).area / 10000.0
        tol = max(0.0001, area_s*1e-8)
        if area_c > area_s + tol or area_l > area_c + tol:
            raise RuntimeError(f'Balance inválido en tesela {tile_id}: {area_s} {area_c} {area_l}')
        results.append(dict(tile_id=tile_id, sensible_ha=area_s,
                            concesionada_ha=area_c, residual_ha=area_l))
        pd.DataFrame(results).to_csv(CHECKPOINT, index=False, encoding='utf-8-sig')
        print(f'  {tile_id}: sensible={area_s:.2f} ha; concedida={area_c:.2f} ha', flush=True)

if not results:
    raise RuntimeError('No hubo teselas con áreas protegidas')
summary = pd.DataFrame(results)
s = summary['sensible_ha'].sum()
c = summary['concesionada_ha'].sum()
l = summary['residual_ha'].sum()
if not (s > 0 and -0.01 <= l <= c+0.01 <= s+0.02):
    raise RuntimeError('Balance final inválido')
out = pd.DataFrame([dict(
    componente='areas_protegidas', n_elementos_originales=len(S),
    superficie_sensible_unica_ha=s,
    superficie_sensible_concesionada_ha=c,
    porcentaje_sensible_concesionada=100*c/s,
    superficie_sensible_residual_provisional_ha=l,
    porcentaje_sensible_residual_provisional=100*l/s,
    estado='PROVISIONAL_OA_SIN_VALIDAR_COCHILCO_SIN_DESCONTAR',
    metodologia='teselas_disjuntas_75km_union_por_tesela',
    n_teselas=len(summary)
)])
out.to_csv(OUTPUT, index=False, encoding='utf-8-sig')
print('\n=== RESULTADO ===\n' + out.to_string(index=False), flush=True)
print('Reporte:', OUTPUT, flush=True)
print('PASO 40b FINALIZADO', flush=True)
