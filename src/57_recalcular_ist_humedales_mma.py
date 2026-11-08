#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 57 — Actualización diferencial del componente HU (12%) del IST.

Reutiliza exactamente las reglas geométricas y los umbrales del paso 43:
  - 1/5/10/25 km -> 1 / .75 / .5 / .25; fuera de 25 km -> 0
  - proyección AEQD local centrada en cada unidad para medir distancias
  - preselección por índice espacial en EPSG:6933 y buffer conservador 200 km
  - huella OA poligonal provisional y punto representativo COCHILCO

La capa 56 nacional sustituye SOLO al componente humedales; los demás
componentes del paso 43 permanecen inalterados. No modifica el paso 43,
los GeoPackage originales ni otras capas de sensibilidad.

Salidas en reports/enmc:
  57_ist_enmc_humedales_mma.csv           (mismo esquema del paso 43)
  57_cambios_ist_humedales_mma.csv       (comparación fila a fila)
  57_resumen_cambios_ist_humedales.csv   (estadísticas por fuente)
  57_control_recalculo_humedales.json    (integridad, método y provenance)

Uso: python -u src/57_recalcular_ist_humedales_mma.py
"""
from __future__ import annotations

import json
import math
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import shapely
from pyproj import CRS, Transformer
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/processed/enmc'
REPORT = ROOT / 'reports/enmc'
OLD = REPORT / '43_ist_enmc.csv'
NEW_HU = BASE / 'sensibilidad/56_humedales_mma_nacional.gpkg'
OA = BASE / 'oa_enmc_candidatas.gpkg'
COCH = BASE / 'cochilco_enmc_proyectos.gpkg'
OUT_FULL = REPORT / '57_ist_enmc_humedales_mma.csv'
OUT_DELTA = REPORT / '57_cambios_ist_humedales_mma.csv'
OUT_SUMMARY = REPORT / '57_resumen_cambios_ist_humedales.csv'
OUT_META = REPORT / '57_control_recalculo_humedales.json'
EXPECTED = {'OA_ENMC': 292, 'COCHILCO_ENMC': 55}
EQAREA = 'EPSG:6933'
WEIGHT_HU = .12
THRESHOLDS = (1, 5, 10, 25)
MAX_BUFFER_M = 200_000


def norm(v):
    s = unicodedata.normalize('NFKD', str(v).casefold())
    return ''.join(c for c in s if not unicodedata.combining(c) and c.isalnum())


def load(path):
    if not path.exists():
        raise FileNotFoundError(f'Falta archivo: {path}')
    g = gpd.read_file(path, engine='pyogrio')
    if g.crs is None:
        raise RuntimeError(f'CRS ausente: {path}')
    if g.geometry.isna().any() or g.geometry.is_empty.any():
        raise RuntimeError(f'Geometrías nulas o vacías en {path}')
    if not g.geometry.is_valid.all():
        # Repetir tratamiento del paso 43 sin alterar fuente
        g.geometry = g.geometry.map(lambda x: shapely.make_valid(x) if not x.is_valid else x)
    return g.to_crs(EQAREA)


def transformer_local(geometry):
    # Equivalente al cálculo del paso 43.
    p_ll = transform(Transformer.from_crs(EQAREA, 'EPSG:4326', always_xy=True).transform,
                     geometry).representative_point()
    local = CRS.from_proj4(
        f'+proj=aeqd +lat_0={p_ll.y:.10f} +lon_0={p_ll.x:.10f} '
        '+datum=WGS84 +units=m +no_defs'
    )
    return Transformer.from_crs(EQAREA, local, always_xy=True).transform


def score_hu(km):
    for score, threshold in zip((1., .75, .5, .25), THRESHOLDS):
        if km <= threshold + 1e-9:
            return score
    return 0.


def validate_old(df):
    required = {'fuente','id_fuente','nombre','IST_01','IST_100','S_HU','A_HU',
                'd_HU_km','candidatos_HU','sin_candidatos_HU'}
    absent = required - set(df.columns)
    if absent:
        raise RuntimeError(f'Columnas ausentes paso 43: {sorted(absent)}')
    counts = df['fuente'].value_counts().to_dict()
    if counts != EXPECTED:
        raise RuntimeError(f'Universo previo inesperado: {counts}; esperado {EXPECTED}')
    if df[['fuente','id_fuente']].duplicated().any():
        raise RuntimeError('Identificadores (fuente,id_fuente) duplicados en paso 43')
    if not np.allclose(df.IST_100, df.IST_01 * 100, atol=1e-5):
        raise RuntimeError('IST_01 e IST_100 no concuerdan en paso 43')
    if not np.allclose(df.A_HU, df.S_HU * 12, atol=1e-6):
        raise RuntimeError('Componente HU inconsistente en el CSV del paso 43')


def source_units():
    oa = load(OA)
    if 'estado_oa_provisional' not in oa.columns or 'OBJECTID' not in oa.columns:
        raise RuntimeError('OA sin campos de estado u OBJECTID')
    oa = oa.loc[oa.estado_oa_provisional.eq('CANDIDATA_OPERACION_POR_TIPO')].copy()
    oa['fuente'] = 'OA_ENMC'
    oa['id_fuente'] = oa.OBJECTID.map(str)
    oa['nombre_calc'] = oa.NOMBRE.map(str)

    coch = load(COCH)
    identifier = next((c for c in ('id_proyecto','ID_PROY','ID','OBJECTID') if c in coch.columns), None)
    if identifier is None:
        coch['id_calculo'] = range(1, len(coch) + 1)
        identifier = 'id_calculo'
    name_col = next((c for c in ('NOMBRE','nombre','PROYECTO','proyecto') if c in coch.columns), None)
    if name_col is None:
        raise RuntimeError('COCHILCO no tiene columna de nombre para validar orden/ID')
    coch['fuente'] = 'COCHILCO_ENMC'
    coch['id_fuente'] = coch[identifier].map(str)
    coch['nombre_calc'] = coch[name_col].map(str)
    units = pd.concat([oa[['fuente','id_fuente','nombre_calc','geometry']],
                       coch[['fuente','id_fuente','nombre_calc','geometry']]], ignore_index=True)
    units = gpd.GeoDataFrame(units, geometry='geometry', crs=EQAREA)
    if units[['fuente','id_fuente']].duplicated().any():
        raise RuntimeError('Identificadores duplicados en capas de unidades')
    counts = units.fuente.value_counts().to_dict()
    if counts != EXPECTED:
        raise RuntimeError(f'Unidades actuales: {counts}; esperado {EXPECTED}')
    return units


def main():
    print('=== PASO 57: ACTUALIZAR IST SOLO HUMEDALES MMA ===', flush=True)
    REPORT.mkdir(parents=True, exist_ok=True)
    old = pd.read_csv(OLD, encoding='utf-8-sig', dtype={'id_fuente': str})
    validate_old(old)
    units = source_units()
    # Los nombres, además de los IDs, permiten detectar una reordenación no deseada.
    check = units.merge(old[['fuente','id_fuente','nombre']], on=['fuente','id_fuente'],
                        how='outer', indicator=True, validate='one_to_one')
    if not check['_merge'].eq('both').all():
        raise RuntimeError('El universo de unidades no coincide con el paso 43')
    mismatches = check.loc[check.apply(lambda r: norm(r.nombre_calc) != norm(r.nombre), axis=1)]
    if not mismatches.empty:
        raise RuntimeError('Nombre/ID no coinciden; verificar estabilidad de IDs COCHILCO. '
                           + str(mismatches[['fuente','id_fuente','nombre_calc','nombre']].head(5).to_dict('records')))

    info = pyogrio.read_info(str(NEW_HU))
    if int(info['features']) != 117969 or str(info['crs']).upper() != EQAREA:
        raise RuntimeError(f'Capa HU nacional inesperada: {info["features"]} y {info["crs"]}')
    print('Cargando humedales nacionales:', info['features'], flush=True)
    hu = load(NEW_HU)[['geometry']].reset_index(drop=True)
    if not hu.geometry.is_valid.all():
        raise RuntimeError('Geometrías de humedales inválidas en capa 56')
    tree = hu.sindex
    print('Unidades a evaluar:', len(units), '| Capa HU:', len(hu), flush=True)

    updated = {}
    for i, row in enumerate(units.itertuples(index=False), start=1):
        geom = row.geometry
        tr = transformer_local(geom)
        g_local = transform(tr, geom)
        candidates = tree.query(geom.envelope.buffer(MAX_BUFFER_M).envelope,
                                predicate='intersects')
        minimum_m = float('inf')
        for idx in candidates:
            g = hu.geometry.iloc[int(idx)]
            if g is None or g.is_empty:
                continue
            d = g_local.distance(transform(tr, g))
            if d < minimum_m:
                minimum_m = d
            if minimum_m <= 1e-7:
                break
        km = minimum_m / 1000
        score = score_hu(km)
        key = (row.fuente, str(row.id_fuente))
        updated[key] = {'d_HU_km': round(km, 6) if math.isfinite(km) else None,
                        'S_HU': score, 'A_HU': round(100 * WEIGHT_HU * score, 6),
                        'candidatos_HU': len(candidates),
                        'sin_candidatos_HU': not math.isfinite(km)}
        if i % 25 == 0 or i == len(units):
            print(f'  {i}/{len(units)} | {row.fuente} | HU={score:.2f} | candidatos={len(candidates)}', flush=True)

    full = old.copy()
    old_sc = full.S_HU.copy()
    old_ist = full.IST_100.copy()
    old_dist = full.d_HU_km.copy()
    for ix, row in full.iterrows():
        result = updated[(row.fuente, str(row.id_fuente))]
        for field, val in result.items():
            full.at[ix, field] = val
    # Mantener los otros componentes del paso 43 exactamente intactos.
    full['IST_100'] = (old_ist + (full.S_HU - old_sc) * (WEIGHT_HU * 100)).round(6)
    full['IST_01'] = (full.IST_100 / 100).round(8)
    if not full.IST_100.between(-1e-6, 100+1e-6).all():
        raise RuntimeError('IST recalculado fuera de 0..100')
    if not np.allclose(full.A_HU, full.S_HU * 12, atol=1e-6):
        raise RuntimeError('A_HU no concuerda con S_HU')
    non_hu_cols = [c for c in old.columns if c not in {'IST_100','IST_01','d_HU_km','S_HU','A_HU','candidatos_HU','sin_candidatos_HU'}]
    if not full[non_hu_cols].equals(old[non_hu_cols]):
        raise RuntimeError('Se alteró alguna columna no dependiente de humedales')
    diff = old[['fuente','id_fuente','nombre']].copy()
    diff['d_HU_anterior_km'] = old_dist
    diff['d_HU_MMA_km'] = full.d_HU_km
    diff['S_HU_anterior'] = old_sc
    diff['S_HU_MMA'] = full.S_HU
    diff['IST_anterior'] = old_ist
    diff['IST_MMA'] = full.IST_100
    diff['delta_IST'] = (diff.IST_MMA - diff.IST_anterior).round(6)
    diff['cambio_HU'] = ~np.isclose(diff.S_HU_anterior, diff.S_HU_MMA)
    diff['cambio_IST'] = ~np.isclose(diff.IST_anterior, diff.IST_MMA, atol=1e-6)
    diff['incremento'] = diff.delta_IST > 0
    diff['disminucion'] = diff.delta_IST < 0
    summary = diff.groupby('fuente', as_index=False).agg(
        n=('delta_IST','size'), n_cambio_hu=('cambio_HU','sum'),
        n_aumento=('incremento','sum'), n_disminucion=('disminucion','sum'),
        ist_antes_prom=('IST_anterior','mean'), ist_mma_prom=('IST_MMA','mean'),
        delta_prom=('delta_IST','mean'), delta_max=('delta_IST','max'),
        delta_min=('delta_IST','min'))

    full.to_csv(OUT_FULL, index=False, encoding='utf-8-sig')
    diff.to_csv(OUT_DELTA, index=False, encoding='utf-8-sig')
    summary.to_csv(OUT_SUMMARY, index=False, encoding='utf-8-sig')
    meta = {
        'paso': 57, 'fecha_utc': datetime.now(timezone.utc).isoformat(),
        'estado': 'recalculo_diferencial_hu_sujeto_a_validacion_tematico_temporal',
        'csv_base': str(OLD.relative_to(ROOT)),
        'humedales_mma': str(NEW_HU.relative_to(ROOT)),
        'universo': EXPECTED, 'numero_humedales': len(hu),
        'componente_actualizado': 'HU', 'peso': WEIGHT_HU,
        'umbrales_km': list(THRESHOLDS),
        'metodo_distancia': 'AEQD local por unidad; preseleccion EPSG:6933 buffer 200km',
        'formula': 'IST_57=IST_43+12*(S_HU_MMA-S_HU_43)',
        'n_alteraciones_hu': int(diff.cambio_HU.sum()),
        'n_alteraciones_ist': int(diff.cambio_IST.sum()),
        'delta_ist_min': float(diff.delta_IST.min()),
        'delta_ist_max': float(diff.delta_IST.max()),
        'nota': 'Los indicadores NO prueban impacto ni condicion operativa; otras capas no auditadas tematicamente. '
                'Las areas humedales y los cruces concesionales NO se recalculan en este script.'
    }
    OUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    print('\n=== RESUMEN DE DIFERENCIAS ===')
    print(summary.to_string(index=False, float_format=lambda v: f'{v:.4f}'))
    print('Salida completa:', OUT_FULL)
    print('Comparación:', OUT_DELTA)
    print('Resumen:', OUT_SUMMARY)
    print('Metadatos:', OUT_META)
    print('PASO 57 FINALIZADO', flush=True)


if __name__ == '__main__':
    main()
