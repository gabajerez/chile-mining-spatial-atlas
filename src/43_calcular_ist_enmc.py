"""Paso 43. IST preliminar ENMC (OA y COCHILCO), 9 componentes.

Distancias planas locales en proyeccion equidistante azimutal (AEQD) centrada
por unidad; indice espacial de preseleccion sobre EPSG:6933, no utilizado
para medir distancias. Los puntajes se basan en nueve pesos del manuscrito.
No equivale a impacto real ni confirma condicion operativa de OA.

Uso: python -u src/43_calcular_ist_enmc.py
     python -u src/43_calcular_ist_enmc.py --limit 10 (prueba, archivos *_PRUEBA)
"""
from __future__ import annotations
import argparse
from pathlib import Path
import json
import math
import warnings

import geopandas as gpd
import pandas as pd
import shapely
from shapely.ops import transform
from pyproj import CRS, Transformer

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/processed/enmc'
SENS = BASE / 'sensibilidad'
REPORT = ROOT / 'reports/enmc'
REPORT.mkdir(parents=True, exist_ok=True)
EQ_AREA = 'EPSG:6933'
MAX_BUFFER_M = 200_000  # Busqueda conservadora, NO distancia final

# Orden de corte 0 <= d <= u1 => 1; u1 < d <= u2 => 0.75, etc.
COMPONENTS = {
    'AP': (('areas_protegidas',), (1, 5, 10, 25), 0.165),
    'SB': (('sitios_prioritarios', 'reservas_biosfera'), (1, 5, 10, 25), 0.099),
    'GL': (('glaciares',), (0.5, 2, 10, 25), 0.133),
    'HU': (('humedales',), (1, 5, 10, 25), 0.120),
    'AI': (('planes_atmosfericos',), (0.5, 5, 25, 50), 0.170),
    'CI': (('comunidades_indigenas',), (2, 10, 25, 50), 0.131),
    'AD': (('areas_desarrollo_indigena',), (2, 10, 25, 50), 0.065),
    'PO': (('areas_pobladas',), (2, 5, 15, 30), 0.070),
    'TU': (('atractivos_turisticos', 'zonas_interes_turistico'), (0.5, 2, 5, 10), 0.047),
}
assert math.isclose(sum(c[2] for c in COMPONENTS.values()), 1.0, abs_tol=1e-10)


def read_layer(path: Path) -> gpd.GeoDataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    df = gpd.read_file(path, engine='pyogrio')
    if df.crs is None:
        raise ValueError(f'CRS no definido: {path}')
    df = df.loc[df.geometry.notna() & ~df.geometry.is_empty].copy()
    if not df.geometry.is_valid.all():
        df['geometry'] = df.geometry.map(lambda g: shapely.make_valid(g))
    return df


def local_transformer(unit_6933):
    unit_ll = transform(Transformer.from_crs(EQ_AREA, 'EPSG:4326', always_xy=True).transform, unit_6933)
    p = unit_ll.representative_point()
    local = CRS.from_proj4(f'+proj=aeqd +lat_0={p.y:.10f} +lon_0={p.x:.10f} +datum=WGS84 +units=m +no_defs')
    return Transformer.from_crs(EQ_AREA, local, always_xy=True).transform


def score(distance_km: float, thresholds):
    for value, limit in zip((1., .75, .5, .25), thresholds):
        if distance_km <= limit + 1e-9:
            return value
    return 0.


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=None, help='Primeras N unidades de cada fuente para prueba')
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error('--limit debe ser >= 1')
    suffix = '_PRUEBA' if args.limit else ''
    print('=== PASO 43: IST ENMC ===', flush=True)
    print('Modo:', 'PRUEBA' if args.limit else 'COMPLETO', flush=True)

    layers = {}
    for names, _, _ in COMPONENTS.values():
        for name in names:
            if name in layers:
                continue
            path = SENS / f'39_{name}.gpkg'
            frame = read_layer(path).to_crs(EQ_AREA)
            frame = frame[['geometry']].reset_index(drop=True)
            # Indexado espacial sin disolver: distancia al mas cercano, NO suma.
            layers[name] = frame
            print(f'Capa {name}: {len(frame)} elementos', flush=True)

    sources = [
        ('OA_ENMC', BASE / 'oa_enmc_candidatas.gpkg'),
        ('COCHILCO_ENMC', BASE / 'cochilco_enmc_proyectos.gpkg'),
    ]
    rows = []
    for group, filename in sources:
        units = read_layer(filename)
        if group == 'OA_ENMC':
            # 31 proyectos/exploracion y 2 revisiones quedan FUERA de la aproximacion a faena.
            units = units.loc[units['estado_oa_provisional'].eq('CANDIDATA_OPERACION_POR_TIPO')].copy()
            if 'OBJECTID' not in units:
                raise ValueError('OA requiere OBJECTID')
            identifier = 'OBJECTID'
        else:
            # Los proyectos COCHILCO son localizaciones representativas puntuales.
            identifier = next((c for c in ('id_proyecto', 'ID_PROY', 'ID', 'OBJECTID') if c in units.columns), None)
            if identifier is None:
                units['id_calculo'] = range(1, len(units) + 1)
                identifier = 'id_calculo'
        print(f'{group}: {len(units)} unidades (antes de limite)', flush=True)
        if args.limit:
            units = units.head(args.limit).copy()
        units = units.to_crs(EQ_AREA)
        for i, (_, rec) in enumerate(units.iterrows(), start=1):
            geometry = rec.geometry
            if geometry is None or geometry.is_empty:
                continue
            tr = local_transformer(geometry)
            local_unit = transform(tr, geometry)
            result = {
                'fuente': group,
                'id_fuente': str(rec[identifier]),
                'nombre': str(next((rec[c] for c in ('NOMBRE', 'nombre', 'PROYECTO', 'proyecto') if c in rec.index), '')),
                'tipo_geometria': geometry.geom_type,
                'estado_operativo': 'NO_CONFIRMADO' if group == 'OA_ENMC' else 'NO_APLICA_PROYECTO',
                'modo_geometria': 'POLIGONO_OA' if group == 'OA_ENMC' else 'PUNTO_REPRESENTATIVO',
            }
            total = 0.
            for code, (names, thresholds, weight) in COMPONENTS.items():
                minimum_m = float('inf')
                candidate_count = 0
                # EPSG:6933 solo preseleccion espacial. El buffer conservador
                # evita eliminar vecinos reales de <=50km por distorsion de EPSG:6933.
                search_geom = geometry.envelope.buffer(MAX_BUFFER_M).envelope
                for name in names:
                    layer = layers[name]
                    hits = layer.sindex.query(search_geom, predicate='intersects')
                    candidate_count += len(hits)
                    if not len(hits):
                        continue
                    # Reproyectar SOLO candidatas, no 26k glaciares para cada OA.
                    for src_geom in layer.geometry.iloc[hits]:
                        if src_geom is None or src_geom.is_empty:
                            continue
                        g_loc = transform(tr, src_geom)
                        d = local_unit.distance(g_loc)
                        if d < minimum_m:
                            minimum_m = d
                        if minimum_m <= 1e-7:
                            break
                    if minimum_m <= 1e-7:
                        break
                km = minimum_m / 1000.
                s = score(km, thresholds)
                result[f'd_{code}_km'] = round(km, 6) if math.isfinite(km) else None
                result[f'S_{code}'] = s
                result[f'A_{code}'] = round(100. * weight * s, 6)
                result[f'candidatos_{code}'] = candidate_count
                result[f'sin_candidatos_{code}'] = not math.isfinite(km)
                total += weight * s
            result['IST_01'] = round(total, 8)
            result['IST_100'] = round(total * 100., 6)
            rows.append(result)
            if i % 20 == 0 or i == len(units):
                print(f'  {group}: {i}/{len(units)} | IST={result["IST_100"]:.2f}', flush=True)

    out = pd.DataFrame(rows)
    if out.empty:
        raise RuntimeError('No se calcularon resultados')
    if not out.IST_100.between(0, 100).all():
        raise RuntimeError('IST fuera de 0..100')
    out_path = REPORT / f'43_ist_enmc{suffix}.csv'
    out.to_csv(out_path, index=False, encoding='utf-8-sig')

    summary = out.groupby('fuente').agg(
        n=('IST_100', 'size'), promedio_ist=('IST_100', 'mean'),
        mediana_ist=('IST_100', 'median'), min_ist=('IST_100', 'min'),
        max_ist=('IST_100', 'max'), n_cero=('IST_100', lambda s: int((s == 0).sum())),
    ).reset_index()
    sum_path = REPORT / f'43_ist_enmc_resumen{suffix}.csv'
    summary.to_csv(sum_path, index=False, encoding='utf-8-sig')
    print(summary.to_string(index=False), flush=True)
    print('Tabla:', out_path, flush=True)
    print('Resumen:', sum_path, flush=True)
    print('NOTA: distancias metricas locales AEQD; selecciones de fuente y OA provisionales.', flush=True)
    print('PASO 43 FINALIZADO', flush=True)


if __name__ == '__main__':
    main()
