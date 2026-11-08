"""Paso 40: superposicion areal, una capa sensible por ejecucion.

Ejemplo:
  python -u src/40_calcular_overlap_sensibilidad.py humedales
  python -u src/40_calcular_overlap_sensibilidad.py glaciares

Resultados PROVISIONALES: OA no verificada y proyectos COCHILCO no descontados.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd
import geopandas as gpd
import shapely

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data' / 'processed' / 'enmc'
SENS = BASE / 'sensibilidad'
REPORT = ROOT / 'reports' / 'enmc'
REPORT.mkdir(parents=True, exist_ok=True)
CRS = 'EPSG:6933'
SUPPORTED = (
    'humedales', 'glaciares', 'areas_protegidas',
    'sitios_prioritarios', 'reservas_biosfera',
    'planes_atmosfericos', 'areas_desarrollo_indigena',
    'areas_pobladas', 'zonas_interes_turistico'
)


def polygonal(g):
    if g is None or g.is_empty:
        return shapely.GeometryCollection()
    if not g.is_valid:
        g = shapely.make_valid(g)
    if g.geom_type in ('Polygon', 'MultiPolygon'):
        return g
    parts = []
    stack = [g]
    while stack:
        node = stack.pop()
        if node.geom_type in ('Polygon', 'MultiPolygon'):
            parts.append(node)
        elif node.geom_type == 'GeometryCollection':
            stack.extend(list(node.geoms))
    return shapely.union_all(parts) if parts else shapely.GeometryCollection()


def union_batches(geoms, batch=500):
    chunks = []
    for start in range(0, len(geoms), batch):
        chunk = [polygonal(x) for x in geoms[start:start+batch]]
        chunk = [x for x in chunk if not x.is_empty]
        if chunk:
            chunks.append(shapely.union_all(chunk))
        print(f'   Union parcial: {min(start+batch, len(geoms))}/{len(geoms)}', flush=True)
    if not chunks:
        raise ValueError('No existen poligonos validos para disolver')
    return polygonal(shapely.union_all(chunks))


def load_single(path):
    if not path.exists():
        raise FileNotFoundError(path)
    df = gpd.read_file(path, engine='pyogrio')
    if df.crs is None or df.crs.to_epsg() != 6933:
        raise ValueError(f'CRS distinto de EPSG:6933: {path} ({df.crs})')
    if df.empty:
        raise ValueError(f'Capa vacia: {path}')
    if len(df) != 1:
        raise ValueError(f'Se esperaba union de una fila: {path} tiene {len(df)}')
    return polygonal(df.geometry.iloc[0])


def main(category):
    print(f'=== PASO 40: {category.upper()} ===', flush=True)
    src = SENS / f'39_{category}.gpkg'
    if not src.exists():
        raise FileNotFoundError(src)
    df = gpd.read_file(src, engine='pyogrio')
    if df.crs is None or df.crs.to_epsg() != 6933:
        raise ValueError(f'CRS no esperado: {df.crs}')
    if df.empty:
        raise ValueError('Capa sensible vacia')
    print(f'Elementos sensibles: {len(df)}', flush=True)
    S = union_batches(list(df.geometry))
    C = load_single(BASE / '35_concesiones_constituidas_ambito.gpkg')
    L = load_single(BASE / '35_concesion_residual_ambito.gpkg')

    if not S.is_valid or not C.is_valid or not L.is_valid:
        raise ValueError('Geometria invalida tras reparacion/disolucion')
    print('Calculando intersecciones con coberturas concesionales...', flush=True)
    SC = polygonal(S.intersection(C))
    SL = polygonal(S.intersection(L))
    area = lambda g: g.area / 10000.0
    aS, aSC, aSL = area(S), area(SC), area(SL)
    if aS <= 0:
        raise ValueError('Area sensible nula')
    tol = max(0.01, aS * 1e-8)
    if aSL > aSC + tol or aSC > aS + tol:
        raise RuntimeError(f'Balance incorrecto: S={aS}, S∩C={aSC}, S∩L={aSL}')
    record = dict(
        componente=category,
        n_elementos_originales=int(len(df)),
        superficie_sensible_unica_ha=aS,
        superficie_sensible_concesionada_ha=aSC,
        porcentaje_sensible_concesionada=100*aSC/aS,
        superficie_sensible_residual_provisional_ha=aSL,
        porcentaje_sensible_residual_provisional=100*aSL/aS,
        estado='PROVISIONAL_OA_SIN_VALIDAR_COCHILCO_SIN_DESCONTAR',
    )
    dest = REPORT / f'40_overlap_{category}.csv'
    pd.DataFrame([record]).to_csv(dest, index=False, encoding='utf-8-sig')
    print(pd.DataFrame([record]).to_string(index=False), flush=True)
    print(f'Reporte: {dest}', flush=True)
    print('PASO 40 FINALIZADO', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('categoria', choices=SUPPORTED)
    args = parser.parse_args()
    main(args.categoria)
