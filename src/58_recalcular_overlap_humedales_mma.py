#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 58: superficie única de humedales MMA y coincidencia con concesiones.

Ámbito: unión de las 343 comunas de estudio. Medición en EPSG:6933.
Descompone el dominio en teselas no superpuestas para evitar disolver los
117.969 humedales en una única operación. La cobertura sensible se disuelve
DENTRO de cada tesela; su área se suma sin doble conteo entre teselas.

Las concesiones constituidas y su residual provisional son geometrías
poligonales de cobertura, NO un inventario de concesiones de minerales críticos.
No modifica fuentes previas ni el IST. Incluye checkpoint para reanudar.

Ejecución: python -u src/58_recalcular_overlap_humedales_mma.py
Opcional:  python -u src/58_recalcular_overlap_humedales_mma.py --tile-km 120
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely
from shapely.geometry import box, GeometryCollection

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/processed/enmc'
REPORT = ROOT / 'reports/enmc'
HU = BASE / 'sensibilidad/56_humedales_mma_nacional.gpkg'
C_FILE = BASE / '35_concesiones_constituidas_ambito.gpkg'
R_FILE = BASE / '35_concesion_residual_ambito.gpkg'
COM_FILE = ROOT / 'data/processed/comunas_consolidadas.gpkg'
OUT_TILES = REPORT / '58_overlap_humedales_mma_teselas.csv'
OUT_SUM = REPORT / '58_overlap_humedales_mma_resumen.csv'
OUT_META = REPORT / '58_overlap_humedales_mma_control.json'
OUT_CHECK = REPORT / '58_overlap_humedales_mma_checkpoint.json'
CRS = 'EPSG:6933'


def polygonal(g):
    if g is None or g.is_empty:
        return GeometryCollection()
    if not g.is_valid:
        g = shapely.make_valid(g)
    if g.geom_type in ('Polygon', 'MultiPolygon'):
        return g
    polys = [p for p in shapely.get_parts(g) if p.geom_type in ('Polygon', 'MultiPolygon') and not p.is_empty]
    return shapely.union_all(polys) if polys else GeometryCollection()


def safe_intersection(a, b):
    if a.is_empty or b.is_empty or not a.intersects(b):
        return GeometryCollection()
    try:
        return polygonal(a.intersection(b))
    except shapely.GEOSException:
        return polygonal(shapely.make_valid(a).intersection(shapely.make_valid(b)))


def load(path, one=False):
    if not path.is_file():
        raise FileNotFoundError(path)
    df = gpd.read_file(path, engine='pyogrio')
    if df.crs is None or df.crs.to_epsg() != 6933:
        raise ValueError(f'CRS != EPSG:6933: {path} -> {df.crs}')
    if one and len(df) != 1:
        raise ValueError(f'Se esperaba 1 geometría disuelta en {path}; hay {len(df)}')
    if not len(df):
        raise ValueError(f'Capa vacía: {path}')
    return df


def signature(tile_m):
    files = [HU, C_FILE, R_FILE, COM_FILE]
    payload = {'tile_m': tile_m, 'files': [
        {'path': str(p.relative_to(ROOT)), 'bytes': p.stat().st_size, 'mtime_ns': p.stat().st_mtime_ns}
        for p in files
    ]}
    value = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return value, payload


def atomic_csv(rows, path):
    tmp = path.with_suffix('.tmp')
    pd.DataFrame(rows).to_csv(tmp, index=False, encoding='utf-8-sig')
    os.replace(tmp, path)


def make_tiles(bounds, size):
    minx, miny, maxx, maxy = bounds
    startx, starty = math.floor(minx / size) * size, math.floor(miny / size) * size
    ix0, ix1 = int(round(startx / size)), math.ceil(maxx / size)
    iy0, iy1 = int(round(starty / size)), math.ceil(maxy / size)
    for i in range(ix0, ix1):
        for j in range(iy0, iy1):
            yield f'{i}_{j}', box(i * size, j * size, (i + 1) * size, (j + 1) * size)


def main(tile_km):
    REPORT.mkdir(parents=True, exist_ok=True)
    size = int(tile_km * 1000)
    sig, sig_data = signature(size)
    print('=== PASO 58: SOLAPAMIENTO HUMEDALES MMA, ÁMBITO COMUNAL ===', flush=True)
    hu = load(HU)
    C = polygonal(load(C_FILE, one=True).geometry.iloc[0])
    R = polygonal(load(R_FILE, one=True).geometry.iloc[0])
    comunas = load(COM_FILE)
    if len(comunas) != 343:
        raise ValueError(f'Se esperaban 343 comunas, se hallaron {len(comunas)}')
    D = polygonal(shapely.union_all([polygonal(g) for g in comunas.geometry]))
    if D.is_empty or not D.is_valid:
        raise ValueError('Dominio comunal inválido')
    if not hu.geometry.is_valid.all():
        raise ValueError('Fuente 56 contiene geometrías inválidas')
    if len(hu) != 117969:
        raise ValueError(f'Registros esperados 117969; observados {len(hu)}')
    if C.is_empty or R.is_empty:
        raise ValueError('Concesiones o residual vacíos')
    print(f'Humedales={len(hu):,}; comunas={len(comunas)}; tile={tile_km:g}km', flush=True)
    print('Ámbito de estudio (ha):', round(D.area / 10000, 2), flush=True)
    grid = [(key, tile) for key, tile in make_tiles(D.bounds, size) if tile.intersects(D)]
    print(f'Teselas que intersectan el ámbito: {len(grid)}', flush=True)

    completed = {}
    if OUT_CHECK.exists():
        check = json.loads(OUT_CHECK.read_text(encoding='utf-8'))
        if check.get('signature') != sig:
            raise RuntimeError('El checkpoint existe pero cambió algún insumo o --tile-km. '
                               'Resguarda o renombra el checkpoint y el CSV antes de reiniciar.')
        if OUT_TILES.exists():
            previous = pd.read_csv(OUT_TILES)
            completed = {str(row['tesela']): row for row in previous.to_dict('records')}
        print(f'Checkpoint compatible: {len(completed)} teselas completas', flush=True)
    else:
        if OUT_TILES.exists():
            raise RuntimeError(f'Existe {OUT_TILES} sin checkpoint: revisar antes de sobrescribir')
        OUT_CHECK.write_text(json.dumps({'signature': sig, 'inputs': sig_data}, indent=2), encoding='utf-8')

    sindex = hu.sindex
    rows = list(completed.values())
    for n, (key, tile) in enumerate(grid, start=1):
        if key in completed:
            continue
        cell = safe_intersection(D, tile)
        if cell.is_empty or cell.area == 0:
            continue
        idx = list(sindex.query(cell, predicate='intersects'))
        pieces = []
        for i in idx:
            geom = hu.geometry.iloc[int(i)]
            part = safe_intersection(geom, cell)
            if not part.is_empty:
                pieces.append(part)
        S = polygonal(shapely.union_all(pieces)) if pieces else GeometryCollection()
        C_cell = safe_intersection(C, cell)
        R_cell = safe_intersection(R, cell)
        SC = safe_intersection(S, C_cell)
        SR = safe_intersection(S, R_cell)
        # Invariantes: residual es subconjunto de constituida, que es subconjunto de S.
        aa, bb, cc = (x.area / 1e4 for x in (S, SC, SR))
        tol = max(0.02, aa * 1e-8)
        if cc > bb + tol or bb > aa + tol:
            raise RuntimeError(f'Balance inconsistente en tesela {key}: S={aa}, SC={bb}, SR={cc}')
        rows.append({
            'tesela': key, 'n_humedales_candidatos': len(idx),
            'superficie_humedales_unica_ha': aa,
            'superficie_humedales_concesionada_ha': bb,
            'superficie_humedales_residual_ha': cc,
            'superficie_humedales_concesionada_coincide_oa_ha': max(0., bb - cc),
        })
        atomic_csv(rows, OUT_TILES)
        print(f'  {n}/{len(grid)} | tesela={key} | candidatos={len(idx)} '
              f'| H={aa:,.2f}ha | H∩C={bb:,.2f}ha | H∩R={cc:,.2f}ha', flush=True)

    df = pd.read_csv(OUT_TILES)
    expected = {key for key, _ in grid}
    if set(df.tesela.astype(str)) != expected or df.tesela.duplicated().any():
        raise RuntimeError('No se completaron todas las teselas previstas')
    area = df[['superficie_humedales_unica_ha', 'superficie_humedales_concesionada_ha',
               'superficie_humedales_residual_ha',
               'superficie_humedales_concesionada_coincide_oa_ha']].sum()
    hs, hc, hr, hoa = (float(v) for v in area)
    if hs <= 0 or hc > hs + 0.05 or hr > hc + 0.05:
        raise RuntimeError('No se cumple el balance nacional')
    out = {
        'componente': 'humedales_mma_nacional',
        'n_elementos_originales': len(hu),
        'n_comunas_ambito': len(comunas),
        'n_teselas': len(grid),
        'superficie_sensible_unica_ha': hs,
        'superficie_sensible_concesionada_ha': hc,
        'porcentaje_sensible_concesionada': 100 * hc / hs,
        'superficie_sensible_residual_provisional_ha': hr,
        'porcentaje_sensible_residual_provisional': 100 * hr / hs,
        'superficie_sensible_concesionada_coincidente_oa_ha': hoa,
        'estado': 'PROVISIONAL_OA_SIN_VALIDAR_COCHILCO_SIN_DESCONTAR',
        'denominador': 'superficie unica del inventario MMA dentro del ambito de 343 comunas',
    }
    pd.DataFrame([out]).to_csv(OUT_SUM, index=False, encoding='utf-8-sig')
    metadata = {
        'paso': 58, 'utc': datetime.now(timezone.utc).isoformat(),
        'crs_areas': CRS, 'area_unidad': 'ha',
        'fuente': str(HU.relative_to(ROOT)),
        'concesiones': str(C_FILE.relative_to(ROOT)),
        'residual': str(R_FILE.relative_to(ROOT)),
        'ambito': str(COM_FILE.relative_to(ROOT)),
        'firma_insumos': sig, 'tile_km': tile_km,
        'procedimiento': 'teselas disjuntas + union por tesela + interseccion espacial exacta',
        'observacion': ('No comparar directamente con paso 40 sin homologar el denominador; '
                        'capas diferentes y 58 restringe superficie sensible al ambito comunal. '
                        'Las capas concesionales son provisionales y no tienen atributo mineral.'),
        'control': out,
    }
    OUT_META.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    print('\n=== RESUMEN NACIONAL DENTRO DEL ÁMBITO COMUNAL ===', flush=True)
    print(pd.DataFrame([out]).to_string(index=False), flush=True)
    print(f'Reportes: {OUT_SUM.name}, {OUT_META.name}, {OUT_TILES.name}', flush=True)
    print('PASO 58 FINALIZADO', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--tile-km', type=float, default=120.)
    args = parser.parse_args()
    if args.tile_km <= 0:
        parser.error('--tile-km debe ser positivo')
    main(args.tile_km)
