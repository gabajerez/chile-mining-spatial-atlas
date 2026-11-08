#!/usr/bin/env python3
"""Paso 55: auditoria del inventario nacional MMA, sin modificar datos originales."""
from pathlib import Path
import json
import sys
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/sensibilidad/humedales_nacional_mma/54_inventario_nacional_humedales.gpkg'
OLD = ROOT / 'data/processed/enmc/sensibilidad/39_humedales.gpkg'
REGIONS = ROOT / 'data/processed/regiones_consolidadas.gpkg'
OUT = ROOT / 'reports/enmc'
OUT.mkdir(parents=True, exist_ok=True)

EXPECTED_SERVER = 117983
EXPECTED_WITH_GEOMETRY = 117969
EXPECTED_MISSING = 14


def inspect_layer(path, label):
    if not path.is_file():
        raise FileNotFoundError(path)
    layers = pyogrio.list_layers(path)
    print(f'{label}: {path}', flush=True)
    print('  capas:', [str(x[0]) for x in layers], flush=True)
    gdf = gpd.read_file(path, engine='pyogrio')
    if gdf.crs is None:
        raise ValueError(f'La capa {label} no tiene CRS: {path}')
    print(f'  registros={len(gdf)} | CRS={gdf.crs}', flush=True)
    return gdf


def geometry_audit(gdf, label):
    types = gdf.geometry.geom_type.value_counts(dropna=False).to_dict()
    missing = int(gdf.geometry.isna().sum())
    empty = int(gdf.geometry.is_empty.sum())
    invalid = int((~gdf.geometry.is_valid & ~gdf.geometry.isna()).sum())
    out = {
        'fuente': label,
        'total_filas': int(len(gdf)),
        'crs': str(gdf.crs),
        'sin_geometria': missing,
        'geometrias_vacias': empty,
        'geometrias_invalidas': invalid,
        'tipos_geom': {str(k): int(v) for k, v in types.items()},
    }
    return out


def count_regions(gdf, regions, label):
    # Solo objetos poligonales, no se descartan silenciosamente al revisar el GPKG.
    good = gdf.geometry.notna() & ~gdf.geometry.is_empty & gdf.geometry.geom_type.isin(['Polygon','MultiPolygon'])
    gdf = gdf.loc[good, ['geometry']].copy()
    gdf = gdf.to_crs(regions.crs)
    # Spatial index: consulta indexada por región sin realizar overlay nacional costoso.
    idx = gdf.sindex
    rows = []
    for _, row in regions.iterrows():
        region_geom = row.geometry
        if region_geom is None or region_geom.is_empty:
            continue
        try:
            hits = idx.query(region_geom, predicate='intersects')
        except Exception as exc:
            # fallback para datasets con geometrías inválidas.
            raise RuntimeError(f'Fallo consulta espacial en {row["nomreg"]}: {exc}') from exc
        rows.append({
            'fuente': label,
            'region': str(row['nomreg']),
            'n_geometrias_intersectan': len(hits),
            'n_geometrias_fuente': len(gdf),
        })
        print(f'  {label} | {row["nomreg"]}: {len(hits):,}', flush=True)
    return pd.DataFrame(rows)


def main():
    print('=== PASO 55: VALIDACION INVENTARIO NACIONAL HUMEDALES ===', flush=True)
    new = inspect_layer(RAW, 'MMA_nacional')
    old = inspect_layer(OLD, 'Inventario_anterior')
    regions = inspect_layer(REGIONS, 'Regiones')
    if 'nomreg' not in regions.columns:
        raise ValueError('No se encuentra el campo nomreg en regiones')
    if len(regions) != 16:
        raise ValueError(f'Se esperaban 16 regiones: {len(regions)}')
    if len(new) != EXPECTED_WITH_GEOMETRY:
        raise ValueError(f'GeoPackage nacional tiene {len(new)} registros, se esperaban {EXPECTED_WITH_GEOMETRY}')
    if EXPECTED_WITH_GEOMETRY + EXPECTED_MISSING != EXPECTED_SERVER:
        raise AssertionError('Reconciliacion de registros incorrecta')

    diagnostics = [geometry_audit(new, 'MMA_nacional'), geometry_audit(old, 'Inventario_anterior')]
    ids = [c for c in new.columns if c.lower() in ('objectid', 'object_id')]
    if ids:
        key = ids[0]
        diagnostics[0]['campo_id'] = key
        diagnostics[0]['ids_nulos'] = int(new[key].isna().sum())
        diagnostics[0]['ids_duplicados'] = int(new[key].duplicated().sum())
        if diagnostics[0]['ids_duplicados'] or diagnostics[0]['ids_nulos']:
            raise ValueError(f'Duplicados/nulos en identificadores del GeoPackage: {key}')
    else:
        diagnostics[0]['advertencia'] = 'No se detecto campo OBJECTID: consultar metadatos de descarga'

    new_ll = new.to_crs(4326)
    diagnostics[0]['bounds_epsg4326'] = [float(x) for x in new_ll.total_bounds]
    old_ll = old.to_crs(4326)
    diagnostics[1]['bounds_epsg4326'] = [float(x) for x in old_ll.total_bounds]

    # Reproyectar límites una sola vez; sin cortar las geometrías fuente.
    regions = regions[['nomreg','geometry']].to_crs('EPSG:6933')
    regional = pd.concat([
        count_regions(new, regions, 'MMA_nacional'),
        count_regions(old, regions, 'Inventario_anterior'),
    ], ignore_index=True)
    dest_csv = OUT / '55_cobertura_regional_humedales_comparativa.csv'
    regional.to_csv(dest_csv, index=False, encoding='utf-8-sig')

    coverage = (regional.assign(presente=lambda d: d.n_geometrias_intersectan.gt(0))
               .groupby('fuente').presente.sum().to_dict())
    diagnostics[0]['regiones_con_presencia'] = int(coverage.get('MMA_nacional', 0))
    diagnostics[1]['regiones_con_presencia'] = int(coverage.get('Inventario_anterior', 0))

    dest_json = OUT / '55_auditoria_inventario_humedales.json'
    dest_json.write_text(json.dumps({
        'paso':55,
        'total_ids_declarados_servicio': EXPECTED_SERVER,
        'ids_con_geometria_reportados_54b':EXPECTED_WITH_GEOMETRY,
        'ids_sin_geometria_reportados_54b':EXPECTED_MISSING,
        'capas': diagnostics,
        'nota': 'Conteos de interseccion regional no son exclusivos; geometria compartida puede contarse en varias regiones. Presencia en regiones no acredita completitud tematica.',
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print('\n=== RESUMEN ===', flush=True)
    for d in diagnostics:
        print(f"{d['fuente']}: {d['total_filas']:,} registros; {d['regiones_con_presencia']}/16 regiones; invalidas={d['geometrias_invalidas']}; vacias={d['geometrias_vacias']}; CRS={d['crs']}", flush=True)
        print('  Bounds lon/lat:', d['bounds_epsg4326'], flush=True)
    print('CSV:', dest_csv, flush=True)
    print('JSON:', dest_json, flush=True)
    print('PASO 55 FINALIZADO', flush=True)

if __name__ == '__main__':
    main()
