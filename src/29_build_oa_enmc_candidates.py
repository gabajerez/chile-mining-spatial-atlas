"""MAPAS_GM - Paso 29: construir capa OA ENMC auditable.
No certifica operacion activa y no altera las capas originales.
Requiere ejecutar antes los scripts 24 y 25.
"""
from pathlib import Path
import json
import re
import unicodedata
import pandas as pd
import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
OA_PATH = ROOT / 'OA-2-Articulo.shp'
REVIEW = ROOT / 'reports/enmc/25_oa_enmc_revision.csv'
OUT = ROOT / 'data/processed/enmc'
REPORT = ROOT / 'reports/enmc'
OUT.mkdir(parents=True, exist_ok=True)
REPORT.mkdir(parents=True, exist_ok=True)

def norm(v):
    x = unicodedata.normalize('NFKD', str(v or '').lower())
    return re.sub(r'\s+', ' ', ''.join(c for c in x if not unicodedata.combining(c))).strip()

if not OA_PATH.exists() or not REVIEW.exists():
    raise FileNotFoundError('Faltan OA original o auditoria 25. Ejecuta scripts 24 y 25.')

oa = gpd.read_file(OA_PATH, engine='pyogrio')
review = pd.read_csv(REVIEW, encoding='utf-8-sig', low_memory=False)
if oa.crs is None:
    raise ValueError('OA no tiene CRS definido')
if 'OBJECTID' not in oa or 'OBJECTID' not in review:
    raise ValueError('Falta OBJECTID para unir OA y auditoria')
if oa['OBJECTID'].duplicated().any() or review['OBJECTID'].duplicated().any():
    raise ValueError('OBJECTID duplicados. No hay union univoca.')
if not review['enmc_si'].fillna(False).astype(bool).all():
    raise ValueError('Revision 25 contiene registros fuera de ENMC')

keep = ['OBJECTID', 'minerales_enmc']
selected = oa.merge(review[keep], on='OBJECTID', how='inner', validate='one_to_one')
if len(selected) != len(review):
    raise ValueError(f'Seleccion incompleta: {len(selected)} de {len(review)}')

def classify_tipo(v):
    t = norm(v)
    if ('proyecto' in t or 'exploracion' in t):
        return 'EXCLUIR_PROYECTO_EXPLORACION'
    if 'extraccion de aridos' in t:
        return 'REVISAR_MINERAL_Y_ACTIVIDAD'
    return 'CANDIDATA_OPERACION_POR_TIPO'

selected['estado_oa_provisional'] = selected['TIPO'].map(classify_tipo)
selected['operacion_confirmada'] = False
selected['revision_requerida'] = True

# Área en una proyección equivalente, sin disolver polígonos individuales.
selected_6933 = selected.to_crs('EPSG:6933')
selected['area_ha_individual'] = selected_6933.geometry.area / 10000.0

# Se conservan todos los 325 registros; no se silencian incertidumbres.
path = OUT / 'oa_enmc_candidatas.gpkg'
if path.exists():
    path.unlink()
selected.to_file(path, layer='oa_enmc_revision', driver='GPKG', engine='pyogrio')

columns = ['OBJECTID','ID_OA','NOMBRE','REGION','COMUNA','MINERAL','minerales_enmc','TIPO','CAT_SERN','estado_oa_provisional','operacion_confirmada','revision_requerida','area_ha_individual']
selected[columns].to_csv(REPORT/'29_oa_enmc_decisiones.csv', index=False, encoding='utf-8-sig')
summary = selected.groupby(['estado_oa_provisional','TIPO'], dropna=False).agg(n_registros=('OBJECTID','size'), suma_areas_individuales_ha=('area_ha_individual','sum')).reset_index()
summary.to_csv(REPORT/'29_oa_enmc_resumen.csv', index=False, encoding='utf-8-sig')

# Inventario de indicadores ya incluidos en OA (sin interpretar su semantica).
sensitivity_cols = [c for c in selected.columns if c.startswith(('S_', 'A_', 'IST_'))]
indicators = []
for c in sensitivity_cols:
    ser = pd.to_numeric(selected[c], errors='coerce')
    indicators.append({'campo':c, 'n_no_nulos':int(ser.notna().sum()), 'n_no_ceros':int(ser.fillna(0).ne(0).sum()), 'min':ser.min(), 'max':ser.max(), 'nota':'Semantica y formula pendientes de verificar con documento metodologico'})
pd.DataFrame(indicators).to_csv(REPORT/'29_inventario_indicadores_sensibilidad_OA.csv', index=False, encoding='utf-8-sig')

print('=== PASO 29: OA ENMC ===')
print('Registros ENMC:', len(selected))
print(selected['estado_oa_provisional'].value_counts().to_string())
print('IMPORTANTE: operacion_confirmada=False para todos hasta validacion')
print('GeoPackage:', path)
print('CSV decisiones:', REPORT/'29_oa_enmc_decisiones.csv')
print('Inventario sensibilidad:', REPORT/'29_inventario_indicadores_sensibilidad_OA.csv')
print('PASO 29 FINALIZADO')
