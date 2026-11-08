#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Auditoria espacial no destructiva: cobertura y CRS del inventario de humedales.

Uso: python -u src/52_auditar_cobertura_humedales.py
No modifica los GeoPackage ni los resultados de pasos anteriores.
"""
from pathlib import Path
import math
import unicodedata
import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_MANIFEST = ROOT / 'reports/enmc/38_inventario_sensibilidad.csv'
RAW_BASE = ROOT / 'data/raw/sensibilidad'
NORMAL = ROOT / 'data/processed/enmc/sensibilidad/39_humedales.gpkg'
REGIONS = ROOT / 'data/processed/regiones_consolidadas.gpkg'
OUT = ROOT / 'reports/enmc'
OUT.mkdir(parents=True, exist_ok=True)

def normalized(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(s).lower())
                   if not unicodedata.combining(c))

def bounds_wgs(gdf):
    b = gdf.to_crs(4326).total_bounds
    return dict(zip(('lon_min','lat_min','lon_max','lat_max'), (float(x) for x in b)))

def audit(label, frame, regions):
    f = frame.to_crs('EPSG:6933')
    rows = []
    print(f'\n--- {label} ---', flush=True)
    print('Registros:', len(f), 'CRS:', frame.crs, 'bounds WGS84:', bounds_wgs(frame),flush=True)
    if 'region' in frame.columns:
        print('Campo region en fuente (primeros 25 valores):', frame['region'].astype(str).value_counts(dropna=False).head(25).to_dict(),flush=True)
    for _, r in regions.iterrows():
        mask = r.geometry
        # Intersections by spatial index; no full national dissolve
        matches = f.sindex.query(mask, predicate='intersects')
        n = int(len(matches))
        rows.append({'conjunto': label, 'region': str(r['nomreg']), 'n_geometrias_intersectan': n})
        print(f'  {str(r["nomreg"]):35s} {n:6d}',flush=True)
    return rows

def main():
    print('=== PASO 52: AUDITORIA DE COBERTURA DE HUMEDALES ===',flush=True)
    manifest = pd.read_csv(RAW_MANIFEST, encoding='utf-8-sig')
    m = manifest.loc[(manifest.categoria == 'humedales') & (manifest.estado == 'OK')]
    if len(m) != 1: raise RuntimeError(f'Se esperaba una fuente de humedales; hay {len(m)}')
    raw_path = RAW_BASE.joinpath(*str(m.iloc[0].archivo).replace('\\','/').split('/'))
    if not raw_path.exists(): raise FileNotFoundError(raw_path)
    raw = gpd.read_file(raw_path, engine='pyogrio')
    norm = gpd.read_file(NORMAL, engine='pyogrio')
    regs = gpd.read_file(REGIONS, engine='pyogrio').to_crs('EPSG:6933')
    if 'nomreg' not in regs or len(regs) != 16: raise ValueError('Se requieren 16 regiones y nomreg')
    if raw.crs is None or norm.crs is None: raise ValueError('Falta CRS; no se asignará uno por suposición')
    print('Fuente:',raw_path,flush=True)
    rows = audit('origen', raw, regs)
    rows += audit('normalizada', norm, regs)
    raw_bounds = bounds_wgs(raw)
    norm_bounds = bounds_wgs(norm)
    span = max(abs(raw_bounds[k]-norm_bounds[k]) for k in raw_bounds)
    print('\nDiferencia máxima bounds WGS84 origen/procesado (grados):',round(span,6),flush=True)
    totals = pd.DataFrame(rows)
    output = OUT/'52_distribucion_regional_humedales.csv'
    totals.to_csv(output,index=False,encoding='utf-8-sig')
    nor = totals.loc[totals.conjunto=='normalizada'].copy()
    north = ['arica','tarapaca','antofagasta','atacama','coquimbo']
    n_north = int(nor.loc[nor.region.map(lambda x:any(z in normalized(x) for z in north)), 'n_geometrias_intersectan'].sum())
    print('\nGeometrias normalizadas que intersectan regiones del norte (suma por region):',n_north,flush=True)
    if n_north == 0:
        print('ALERTA: el insumo de humedales normalizado NO representa cobertura nacional utilizable sin verificar fuente y CRS.',flush=True)
        print('No interpretar el 35,66 % como porcentaje nacional de todos los humedales de Chile.',flush=True)
    else:
        print('Hay registros en el norte: revisar cobertura por region y categorias antes de interpretar el porcentaje nacional.',flush=True)
    print('REPORTE:',output,flush=True)
    print('PASO 52 FINALIZADO',flush=True)

if __name__ == '__main__': main()
