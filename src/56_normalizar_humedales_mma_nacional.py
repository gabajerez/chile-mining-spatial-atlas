#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 56: normalización conservadora del Inventario Nacional de Humedales MMA.

Entrada:  data/raw/sensibilidad/humedales_nacional_mma/54_inventario_nacional_humedales.gpkg
Salida:   data/processed/enmc/sensibilidad/56_humedales_mma_nacional.gpkg
Control:  reports/enmc/56_control_normalizacion_humedales.json

No sustituye 39_humedales.gpkg ni recalcula el IST o solapamientos.
Mantiene todos los atributos y OBJECTID; almacena geometrías MultiPolygon
homogéneas, válidas, bidimensionales, en EPSG:6933. Procesa por lotes para
limitar memoria y valida la correspondencia completa de identificadores.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
from shapely import force_2d
from shapely.geometry import MultiPolygon

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/raw/sensibilidad/humedales_nacional_mma/54_inventario_nacional_humedales.gpkg'
DEST = ROOT / 'data/processed/enmc/sensibilidad/56_humedales_mma_nacional.gpkg'
REPORT = ROOT / 'reports/enmc/56_control_normalizacion_humedales.json'
METADATA_54B = ROOT / 'reports/enmc/54b_inventario_nacional_humedales_metadatos.json'
LAYER_SRC = 'humedales_mma'
LAYER_DEST = 'humedales'
EXPECTED = 117969


def json_safe(value):
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return str(value)


def normalized(geom, oid):
    if geom is None or geom.is_empty:
        raise ValueError(f'OBJECTID={oid}: geometría ausente/vacía')
    geom = force_2d(geom)
    if not geom.is_valid:
        raise ValueError(f'OBJECTID={oid}: geometría inválida en fuente ya validada')
    if geom.geom_type == 'Polygon':
        out = MultiPolygon([geom])
    elif geom.geom_type == 'MultiPolygon':
        out = geom
    else:
        raise ValueError(f'OBJECTID={oid}: tipo inesperado {geom.geom_type}')
    if out.is_empty or not out.is_valid or out.area <= 0:
        raise ValueError(f'OBJECTID={oid}: no admite MultiPolygon válido con área')
    return out


def ids_from_gpkg(path: Path, layer: str):
    # GeoPackage con columnas de atributos: evita cargar nuevamente las geometrías.
    frame = pyogrio.read_dataframe(str(path), layer=layer,
                                  columns=['OBJECTID'], read_geometry=False)
    if 'OBJECTID' not in frame.columns:
        raise ValueError(f'Falta OBJECTID en {path}')
    ids = pd.to_numeric(frame['OBJECTID'], errors='raise').astype('int64')
    if ids.isna().any() or ids.duplicated().any():
        raise ValueError(f'OBJECTID nulos o duplicados en {path}')
    return set(map(int, ids)), len(ids)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch-size', type=int, default=5000,
                        help='Registros por lote (500 a 10000; predeterminado 5000)')
    args = parser.parse_args()
    if not 500 <= args.batch_size <= 10000:
        parser.error('--batch-size debe estar entre 500 y 10000')

    print('=== PASO 56: NORMALIZACION HUMEDALES MMA NACIONAL ===', flush=True)
    if not SOURCE.is_file():
        raise FileNotFoundError(f'No existe la descarga validada: {SOURCE}')
    if DEST.exists():
        raise FileExistsError(f'La salida ya existe y no se sobrescribirá: {DEST}')
    temp = DEST.with_name('56_humedales_mma_nacional.incompleto.gpkg')
    if temp.exists():
        raise FileExistsError('Existe una salida incompleta anterior. Revisar o apartar manualmente: ' + str(temp))
    DEST.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)

    source_info = pyogrio.read_info(str(SOURCE), layer=LAYER_SRC)
    n_expected = int(source_info['features'])
    if n_expected != EXPECTED:
        raise ValueError(f'Se esperaban {EXPECTED} registros; fuente tiene {n_expected}')
    print(f'Fuente: {n_expected:,} registros; CRS={source_info.get("crs")}', flush=True)
    original_ids, n_ids = ids_from_gpkg(SOURCE, LAYER_SRC)
    if n_ids != n_expected:
        raise ValueError('IDs y conteo del GeoPackage fuente no coinciden')
    if 'OBJECTID' not in source_info['fields']:
        raise ValueError('La fuente carece de OBJECTID')

    total = 0
    total_area_ha = 0.0
    initial_types = Counter()
    written_ids = set()
    for offset in range(0, n_expected, args.batch_size):
        frame = pyogrio.read_dataframe(str(SOURCE), layer=LAYER_SRC,
                                      skip_features=offset,
                                      max_features=min(args.batch_size, n_expected - offset))
        if frame.empty:
            raise RuntimeError(f'Lectura vacía inesperada en offset={offset}')
        if frame.crs is None:
            raise ValueError('Un lote no contiene CRS definido')
        if str(frame.crs).upper() != 'EPSG:4326':
            raise ValueError(f'CRS fuente inesperado: {frame.crs}')
        ids = pd.to_numeric(frame['OBJECTID'], errors='raise').astype('int64')
        if ids.isna().any() or ids.duplicated().any():
            raise ValueError(f'OBJECTID inválidos en lote desde {offset}')
        batch_ids = set(map(int, ids))
        if written_ids & batch_ids:
            raise ValueError('IDs repetidos entre lotes')
        initial_types.update(frame.geometry.geom_type.value_counts().to_dict())
        frame.geometry = [normalized(geom, int(oid))
                          for geom, oid in zip(frame.geometry, ids)]
        # La fuente es WGS84: to_crs transforma las coordenadas, no solo etiqueta CRS.
        projected = frame.to_crs('EPSG:6933')
        if projected.crs is None or projected.crs.to_epsg() != 6933:
            raise RuntimeError('La reproyección a EPSG:6933 no se realizó')
        valid = projected.geometry.is_valid
        if not valid.all() or projected.geometry.is_empty.any():
            raise ValueError(f'Problema de validez tras reproyectar lote {offset}')
        if not projected.geometry.geom_type.eq('MultiPolygon').all():
            raise ValueError('No se normalizaron todos los tipos a MultiPolygon')
        areas = projected.geometry.area
        if not (areas > 0).all():
            raise ValueError('Área nula/negativa tras proyección')
        total_area_ha += float(areas.sum() / 10000)
        # La escritura se realiza en archivo temporal y el nombre final solo
        # aparece si se verificó la integridad de todos los lotes.
        projected.to_file(str(temp), layer=LAYER_DEST, driver='GPKG',
                          engine='pyogrio', index=False, append=temp.exists(),
                          geometry_type='MultiPolygon')
        written_ids.update(batch_ids)
        total += len(projected)
        print(f'  Normalizados: {total:,}/{n_expected:,}', flush=True)
        del frame, projected

    if total != n_expected or written_ids != original_ids:
        raise RuntimeError('Conteo o set de OBJECTID no coincide con fuente')
    dest_info = pyogrio.read_info(str(temp), layer=LAYER_DEST)
    if int(dest_info['features']) != n_expected:
        raise RuntimeError('El GeoPackage temporal no conserva todas las filas')
    if str(dest_info['crs']).upper() != 'EPSG:6933':
        raise RuntimeError(f'CRS de salida incorrecto: {dest_info["crs"]}')
    dest_ids, count_dest = ids_from_gpkg(temp, LAYER_DEST)
    if count_dest != n_expected or dest_ids != original_ids:
        raise RuntimeError('Verificación de IDs en disco no coincide')
    if 'MULTIPOLYGON' not in str(dest_info.get('geometry_type', '')).upper():
        raise RuntimeError('Capa final no declara tipo MultiPolygon')

    # Renombrado atómico dentro del mismo volumen, una vez verificado todo.
    os.replace(temp, DEST)
    previous_metadata = {}
    if METADATA_54B.exists():
        previous_metadata = json.loads(METADATA_54B.read_text(encoding='utf-8'))
    report = {
        'paso': 56,
        'estado': 'validado_estructura_pendiente_validacion_tematica',
        'fecha_utc': datetime.now(timezone.utc).isoformat(),
        'fuente': str(SOURCE.relative_to(ROOT)),
        'destino': str(DEST.relative_to(ROOT)),
        'url_origen': previous_metadata.get('url_servicio'),
        'layer_origen': LAYER_SRC,
        'layer_destino': LAYER_DEST,
        'crs_origen': 'EPSG:4326',
        'crs_destino': 'EPSG:6933',
        'tipo_geometria_salida': 'MultiPolygon',
        'n_registros_entrada': n_expected,
        'n_registros_salida': count_dest,
        'objectid_iguales': True,
        'tipos_geometria_entrada': dict(initial_types),
        'area_total_no_disuelta_ha': round(total_area_ha, 4),
        'nota_area': 'Suma de áreas individuales (puede contar solapamientos); no es superficie nacional única.',
        'advertencia': 'No reemplaza 39_humedales.gpkg ni valida la equivalencia temática, categorías o fecha de la fuente. No recalcula IST.',
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Archivo normalizado: {DEST}', flush=True)
    print(f'Control: {REPORT}', flush=True)
    print(f'ID verificados: {count_dest:,} | Geometría: MultiPolygon | CRS: EPSG:6933', flush=True)
    print('PASO 56 FINALIZADO', flush=True)


if __name__ == '__main__':
    main()
