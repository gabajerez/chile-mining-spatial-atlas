"""Paso 32: concesion residual PROVISIONAL (criterios ENMC).

No constituye la estimacion definitiva del manuscrito: usa candidatas OA,
no operaciones confirmadas, y no descuenta proyectos COCHILCO sin poligonos.
"""
from pathlib import Path
import json
import time
import pandas as pd
import geopandas as gpd
import shapely

ROOT = Path(__file__).resolve().parents[1]
CON_PATH = ROOT / 'data/processed/concesiones_final_6933.gpkg'
OA_PATH = ROOT / 'data/processed/enmc/oa_enmc_candidatas.gpkg'
PROCESSED = ROOT / 'data/processed/enmc'
REPORTS = ROOT / 'reports/enmc'
PROCESSED.mkdir(parents=True, exist_ok=True)
REPORTS.mkdir(parents=True, exist_ok=True)
CRS = 'EPSG:6933'


def normalized(s):
    return s.fillna('').astype(str).str.strip().str.upper().str.replace('Ó', 'O', regex=False)


def fix_geometry(g):
    if g is None or g.is_empty:
        return None
    if not g.is_valid:
        g = shapely.make_valid(g)
    # only polygonal pieces matter (repairs may yield GeometryCollection)
    polys = [part for part in shapely.get_parts(g) if part.geom_type in ('Polygon', 'MultiPolygon')]
    return shapely.union_all(polys) if polys else None


def dissolve(geometries, tag):
    """Union in batches, then union batches; avoids a single enormous input array."""
    batch_size = 1500
    batches = []
    all_geoms = [x for x in geometries if x is not None and not x.is_empty]
    print(f'{tag}: {len(all_geoms)} geometrías; unión en lotes', flush=True)
    for i in range(0, len(all_geoms), batch_size):
        batches.append(shapely.union_all(all_geoms[i:i+batch_size]))
        if (i // batch_size) % 10 == 0:
            print(f'  lotes terminados: {min(i + batch_size, len(all_geoms))}/{len(all_geoms)}', flush=True)
    return shapely.union_all(batches)


t0 = time.monotonic()
print('=== PASO 32 / CONCESION LATENTE PROVISIONAL ===', flush=True)

if not CON_PATH.is_file() or not OA_PATH.is_file():
    raise FileNotFoundError('Falta archivo de concesiones o de candidatas OA (paso 29)')

con = gpd.read_file(CON_PATH, engine='pyogrio')
if con.crs is None:
    raise ValueError('Concesiones sin CRS')
con = con.to_crs(CRS)
if 'SITUACION_CONCESION' not in con.columns:
    raise ValueError('Falta campo SITUACION_CONCESION')
con = con.loc[normalized(con['SITUACION_CONCESION']) == 'CONSTITUIDA'].copy()
if len(con) != 83522:
    print(f'ADVERTENCIA: se esperaban 83522 concesiones y hay {len(con)}; revisar origen', flush=True)
if 'TIPO_CONCESION' in con:
    print('Tipos:', con['TIPO_CONCESION'].value_counts(dropna=False).to_dict(), flush=True)

con_geoms = [fix_geometry(x) for x in con.geometry]
union_path = PROCESSED / '32_union_concesiones_constituidas.gpkg'
if union_path.is_file():
    print('Usando union concesional de ejecución anterior:', union_path, flush=True)
    prior = gpd.read_file(union_path, layer='union_concesiones', engine='pyogrio')
    if prior.crs is None or str(prior.crs) != CRS or len(prior) != 1:
        raise ValueError('La unión existente no es válida para reutilización')
    C = prior.geometry.iloc[0]
else:
    C = dissolve(con_geoms, 'Concesiones')
    gpd.GeoDataFrame({'etapa':['constituidas_disueltas']}, geometry=[C], crs=CRS).to_file(
        union_path, layer='union_concesiones', driver='GPKG', engine='pyogrio')

OA = gpd.read_file(OA_PATH, engine='pyogrio')
if OA.crs is None:
    raise ValueError('OA sin CRS')
OA = OA.to_crs(CRS)
if 'estado_oa_provisional' not in OA.columns:
    raise ValueError('Falta estado_oa_provisional en OA')
OA = OA.loc[OA['estado_oa_provisional'] == 'CANDIDATA_OPERACION_POR_TIPO'].copy()
if len(OA) != 292:
    print(f'ADVERTENCIA: esperadas 292 OA candidatas; hay {len(OA)}', flush=True)

O = dissolve([fix_geometry(g) for g in OA.geometry], 'OA candidatas')
L = C.difference(O)
if not L.is_valid:
    L = shapely.make_valid(L)

c_ha = C.area/10000
l_ha = L.area/10000
removed_ha = c_ha-l_ha
inter_ha = C.intersection(O).area/10000
if not abs(removed_ha-inter_ha) < max(0.05, c_ha*1e-8):
    raise AssertionError('Diferencia de áreas no consistente: revisar geometrías')
if l_ha < -0.01 or l_ha > c_ha+0.01:
    raise AssertionError('Área residual inválida')

out = PROCESSED / '32_concesion_residual_provisional.gpkg'
gpd.GeoDataFrame(
    {'estado':['RESIDUAL_PROVISIONAL'], 'nota':['Constituidas menos OA candidatas; COCHILCO sin descontar']},
    geometry=[L], crs=CRS
).to_file(out, layer='residual_provisional', driver='GPKG', engine='pyogrio')

summary = pd.DataFrame([{
    'n_concesiones_constituidas':len(con),
    'n_poligonos_oa_candidatos':len(OA),
    'area_union_concesiones_ha':c_ha,
    'area_descuento_oa_en_concesiones_ha':removed_ha,
    'area_residual_provisional_ha':l_ha,
    'pct_residual_de_union_concesiones':l_ha/c_ha*100,
    'operaciones_confirmadas':False,
    'cochilco_nuevos_descontados':False,
    'es_resultado_definitivo':False,
}])
report = REPORTS/'32_concesion_residual_provisional_resumen.csv'
summary.to_csv(report,index=False,encoding='utf-8-sig')
print('\n=== RESULTADO PROVISIONAL ===', flush=True)
print(summary.to_string(index=False), flush=True)
print('Capa residual:',out, flush=True)
print('Informe:',report, flush=True)
print(f'Duración: {(time.monotonic()-t0)/60:.1f} min', flush=True)
print('PASO 32 FINALIZADO (NO ES RESULTADO DEFINITIVO)', flush=True)
