"""Audita concesiones constituidas para el atlas ENMC según criterios metodológicos del módulo ENMC.
No asigna minerales, no afirma superficies latentes definitivas.
"""
from pathlib import Path
import unicodedata
import pandas as pd
import geopandas as gpd
import pyogrio

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/processed/concesiones_final_6933.gpkg'
OUT = ROOT / 'reports/enmc'
OUT.mkdir(parents=True, exist_ok=True)


def norm(v):
    if pd.isna(v): return ''
    s = unicodedata.normalize('NFKD', str(v)).upper().strip()
    return ''.join(c for c in s if not unicodedata.combining(c))

if not SOURCE.exists():
    raise FileNotFoundError(f'No existe {SOURCE}')
info = pyogrio.read_info(SOURCE)
required = {'SITUACION_CONCESION', 'TIPO_CONCESION'}
missing = required - set(info['fields'])
if missing:
    raise ValueError(f'Faltan campos requeridos: {sorted(missing)}')

attrs = gpd.read_file(SOURCE, engine='pyogrio', ignore_geometry=True,
                      columns=['SITUACION_CONCESION','TIPO_CONCESION'])
attrs['situacion_norm'] = attrs['SITUACION_CONCESION'].map(norm)
attrs['tipo_norm'] = attrs['TIPO_CONCESION'].map(norm)

def is_constituted(v):
    return v in {'CONSTITUIDA', 'CONSTITUIDO', 'CONSTITUIDAS', 'CONSTITUIDOS'}

attrs['incluida_base'] = attrs['situacion_norm'].map(is_constituted)
if not attrs['incluida_base'].any():
    raise ValueError('Ninguna concesion coincide con valores constituidos; revisar codificacion')

summary = (attrs.groupby(['situacion_norm','tipo_norm','incluida_base'], dropna=False)
           .size().reset_index(name='n_registros')
           .sort_values(['incluida_base','situacion_norm','tipo_norm'], ascending=[False,True,True]))
summary.to_csv(OUT / '31_concesiones_atributos.csv', index=False, encoding='utf-8-sig')

# No se suman HECTAREAS ni areas individuales: los derechos pueden solaparse.
print('=== PASO 31 / AUDITORIA CONCESIONES ===', flush=True)
print('Fuente:', SOURCE)
print('Registros totales:', len(attrs))
print('Registros constituidos:', int(attrs['incluida_base'].sum()))
print('CRS de la fuente:', info['crs'])
print(summary.to_string(index=False))
print('\nADVERTENCIA: cantidad de concesiones no equivale a superficie sin doble conteo.')
print('ADVERTENCIA: no se asignan minerales a los derechos.')
print('ADVERTENCIA: latente definitivo requiere restar OA operativo validado y poligonos COCHILCO nuevos.')
print('Archivo:', OUT / '31_concesiones_atributos.csv')
print('PASO 31 AUDITORIA FINALIZADA', flush=True)
