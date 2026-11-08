#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 56b. Reanuda normalización MMA sin perder 110.000 registros ya escritos.

Entrada original: 54_inventario_nacional_humedales.gpkg (EPSG:4326).
Salida parcial: 56_humedales_mma_nacional.incompleto.gpkg (EPSG:6933).
Salida final: 56_humedales_mma_nacional.gpkg.

Conserva OBJECTID y atributos; geometría 2D MultiPolygon. Intenta reparar
solo geometrías que sean inválidas DESPUÉS de reproyectar; registra reparaciones
por OBJECTID y variación de área. No altera las capas originales ni el IST.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
from shapely import force_2d, make_valid
from shapely.geometry import MultiPolygon
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'data/raw/sensibilidad/humedales_nacional_mma/54_inventario_nacional_humedales.gpkg'
DEST = ROOT / 'data/processed/enmc/sensibilidad/56_humedales_mma_nacional.gpkg'
TEMP = DEST.with_name('56_humedales_mma_nacional.incompleto.gpkg')
REPORT = ROOT / 'reports/enmc/56b_control_normalizacion_humedales.json'
REPAIRS = ROOT / 'reports/enmc/56b_reparaciones_geometricas.csv'
LAYER_SRC = 'humedales_mma'
LAYER_DST = 'humedales'
EXPECTED = 117969


def ids(path, layer):
    df = pyogrio.read_dataframe(str(path), layer=layer,
                                columns=['OBJECTID'], read_geometry=False)
    if 'OBJECTID' not in df.columns:
        raise RuntimeError(f'Falta campo OBJECTID en {path}')
    x = pd.to_numeric(df.OBJECTID, errors='raise')
    if x.isna().any() or x.duplicated().any():
        raise RuntimeError(f'OBJECTID ausente/duplicado en {path}')
    if (x % 1 != 0).any():
        raise RuntimeError(f'OBJECTID no entero en {path}')
    return set(int(v) for v in x), len(x)


def polygons_only(geom):
    """Obtiene solo partes poligonales; no crea polígonos a partir de líneas."""
    if geom.is_empty:
        return []
    if geom.geom_type == 'Polygon':
        return [geom] if geom.area > 0 else []
    if geom.geom_type == 'MultiPolygon':
        return [p for p in geom.geoms if not p.is_empty and p.area > 0]
    if geom.geom_type == 'GeometryCollection':
        result = []
        for part in geom.geoms:
            result.extend(polygons_only(part))
        return result
    return []


def to_multipolygon(geom, oid, allow_repair, records, max_area_change_pct):
    if geom is None or geom.is_empty:
        raise ValueError(f'OBJECTID {oid}: geometría vacía')
    geom = force_2d(geom)
    if geom.is_valid:
        parts = polygons_only(geom)
        if not parts:
            raise ValueError(f'OBJECTID {oid}: sin polígonos utilizables')
        out = MultiPolygon(parts)
        if not out.is_valid or out.is_empty or out.area <= 0:
            raise ValueError(f'OBJECTID {oid}: MultiPolygon inválido')
        return out
    if not allow_repair:
        raise ValueError(f'OBJECTID {oid}: geometría original inválida')
    old_area = geom.area
    fixed = make_valid(geom)
    parts = polygons_only(fixed)
    if not parts:
        raise ValueError(f'OBJECTID {oid}: make_valid no recuperó polígonos')
    # Dissolve solo si las partes reparadas se superponen.
    candidate = MultiPolygon(parts)
    if not candidate.is_valid:
        merged = unary_union(parts)
        parts = polygons_only(merged)
        candidate = MultiPolygon(parts)
    if candidate.is_empty or not candidate.is_valid or candidate.area <= 0:
        raise ValueError(f'OBJECTID {oid}: reparación no produjo geometría válida')
    change_pct = abs(candidate.area - old_area) / old_area * 100 if old_area > 0 else float('inf')
    records.append({'OBJECTID': int(oid),
                    'tipo_antes': geom.geom_type,
                    'tipo_despues': candidate.geom_type,
                    'area_pre_reparacion_ha': old_area / 10000,
                    'area_post_reparacion_ha': candidate.area / 10000,
                    'variacion_area_porcentaje': change_pct})
    if change_pct > max_area_change_pct:
        raise ValueError(f'OBJECTID {oid}: reparación altera área en {change_pct:.4f}% '
                         f'(umbral {max_area_change_pct}%). Revisar manualmente.')
    return candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch-size', type=int, default=5000)
    parser.add_argument('--max-area-change-pct', type=float, default=0.1,
                        help='Umbral máximo para reparación geométrica, en %% (def. 0.1)')
    args = parser.parse_args()
    if not 200 <= args.batch_size <= 10000 or args.max_area_change_pct < 0:
        parser.error('batch-size debe estar entre 200 y 10000 y umbral no negativo')

    print('=== PASO 56b: REANUDAR NORMALIZACION HUMEDALES ===', flush=True)
    if not SRC.exists():
        raise FileNotFoundError(SRC)
    if DEST.exists():
        raise FileExistsError(f'El archivo definitivo ya existe: {DEST}. No se sobrescribe.')
    if not TEMP.exists():
        raise FileNotFoundError(f'No existe archivo parcial recuperable: {TEMP}')
    src_info = pyogrio.read_info(str(SRC), layer=LAYER_SRC)
    temp_info = pyogrio.read_info(str(TEMP), layer=LAYER_DST)
    if int(src_info['features']) != EXPECTED or str(src_info['crs']).upper() != 'EPSG:4326':
        raise RuntimeError('Fuente inesperada: recuento o CRS incorrecto')
    if str(temp_info['crs']).upper() != 'EPSG:6933':
        raise RuntimeError(f'CRS del parcial incorrecto: {temp_info["crs"]}')
    orig_ids, n_orig = ids(SRC, LAYER_SRC)
    saved_ids, saved_n = ids(TEMP, LAYER_DST)
    if not saved_ids <= orig_ids:
        raise RuntimeError('El parcial tiene OBJECTID ajenos a la fuente')
    print(f'Fuente: {n_orig:,} | Ya normalizados: {saved_n:,} | '
          f'Pendientes: {n_orig - saved_n:,}', flush=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    repairs = []
    processed = 0
    for offset in range(0, n_orig, args.batch_size):
        frame = pyogrio.read_dataframe(str(SRC), layer=LAYER_SRC,
                                       skip_features=offset,
                                       max_features=min(args.batch_size, n_orig-offset))
        if frame.empty:
            raise RuntimeError(f'Lote fuente vacío en offset {offset}')
        if frame.crs is None or frame.crs.to_epsg() != 4326:
            raise RuntimeError(f'CRS incorrecto en lote {offset}')
        id_series = pd.to_numeric(frame.OBJECTID, errors='raise').astype('int64')
        todo = ~id_series.isin(saved_ids)
        if not todo.any():
            continue
        frame = frame.loc[todo].copy()
        id_series = id_series.loc[todo]
        frame.geometry = [to_multipolygon(g, int(oid), False, [], args.max_area_change_pct)
                          for g, oid in zip(frame.geometry, id_series)]
        frame = frame.to_crs('EPSG:6933')
        # Primero detectar y registrar, luego recuperar en cada OBJECTID.
        repaired_geoms = []
        for geom, oid in zip(frame.geometry, id_series):
            repaired_geoms.append(to_multipolygon(
                geom, int(oid), True, repairs, args.max_area_change_pct))
        frame.geometry = repaired_geoms
        if frame.geometry.is_empty.any() or not frame.geometry.is_valid.all():
            raise RuntimeError(f'Persisten geometrías inválidas en offset {offset}')
        if not frame.geometry.geom_type.eq('MultiPolygon').all():
            raise RuntimeError('Tipo geométrico no homogéneo')
        if not (frame.geometry.area > 0).all():
            raise RuntimeError('Área cero tras transformar')
        frame.to_file(str(TEMP), layer=LAYER_DST, driver='GPKG',
                      engine='pyogrio', index=False, append=True,
                      geometry_type='MultiPolygon')
        these = set(int(x) for x in id_series)
        if these & saved_ids:
            raise RuntimeError('Duplicación inesperada de OBJECTID')
        saved_ids.update(these)
        processed += len(frame)
        print(f'  Incorporados en esta ejecución: {processed:,} | '
              f'Acumulados: {len(saved_ids):,}/{n_orig:,} | '
              f'Reparaciones: {len(repairs)}', flush=True)

    # Dejar evidencia de las reparaciones incluso si falla la validación final.
    pd.DataFrame(repairs, columns=['OBJECTID','tipo_antes','tipo_despues',
                                   'area_pre_reparacion_ha','area_post_reparacion_ha',
                                   'variacion_area_porcentaje']).to_csv(REPAIRS, index=False, encoding='utf-8-sig')
    disk_ids, disk_n = ids(TEMP, LAYER_DST)
    final_info = pyogrio.read_info(str(TEMP), layer=LAYER_DST)
    if disk_n != n_orig or disk_ids != orig_ids or int(final_info['features']) != n_orig:
        missing = orig_ids - disk_ids
        extra = disk_ids - orig_ids
        raise RuntimeError(f'Integridad final fallida: {disk_n}/{n_orig}; '
                           f'faltantes={len(missing)}, extras={len(extra)}')
    if str(final_info['crs']).upper() != 'EPSG:6933':
        raise RuntimeError('CRS final incorrecto')
    if 'MULTIPOLYGON' not in str(final_info.get('geometry_type', '')).upper():
        raise RuntimeError('Esquema de capa final no es MultiPolygon')
    # Verificar geometrías del disco por lotes (también los 110.000 previos).
    invalid_disk, empty_disk, wrong_types = 0, 0, 0
    for offset in range(0, n_orig, args.batch_size):
        sub = pyogrio.read_dataframe(str(TEMP), layer=LAYER_DST,
                                    skip_features=offset,
                                    max_features=min(args.batch_size, n_orig-offset),
                                    columns=['OBJECTID'])
        invalid_disk += int((~sub.geometry.is_valid).sum())
        empty_disk += int(sub.geometry.is_empty.sum())
        wrong_types += int((sub.geometry.geom_type != 'MultiPolygon').sum())
    if invalid_disk or empty_disk or wrong_types:
        raise RuntimeError(f'Problemas de geometría en disco: invalidas={invalid_disk}, '
                           f'vacias={empty_disk}, tipos_no_multipolygon={wrong_types}')
    report = {
        'paso': '56b', 'fecha_utc': datetime.now(timezone.utc).isoformat(),
        'estado': 'geometria_y_ids_validados_pendiente_revision_tematica',
        'fuente': str(SRC.relative_to(ROOT)),
        'destino': str(DEST.relative_to(ROOT)),
        'registros_fuente': n_orig, 'recuperados_de_ejecucion_anterior': saved_n,
        'registros_agregados_56b': processed, 'registros_finales': disk_n,
        'objectid_concordantes': disk_ids == orig_ids, 'crs': final_info['crs'],
        'geometrias_invalidas_disco': invalid_disk,
        'geometrias_vacias_disco': empty_disk,
        'tipos_no_multipolygon_disco': wrong_types,
        'reparaciones_56b': len(repairs),
        'max_variacion_area_reparacion_pct': max((r['variacion_area_porcentaje'] for r in repairs), default=0),
        'umbral_variacion_area_pct': args.max_area_change_pct,
        'observaciones': 'Se preserva capa 39 y no se recalculan IST ni superposiciones. Revisar cobertura temática y 14 registros sin geometría del paso 54b.'
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(TEMP, DEST)
    print(f'Final: {DEST}', flush=True)
    print(f'Informe: {REPORT}', flush=True)
    print(f'Reparaciones: {REPAIRS}', flush=True)
    print('PASO 56b FINALIZADO', flush=True)


if __name__ == '__main__':
    main()
