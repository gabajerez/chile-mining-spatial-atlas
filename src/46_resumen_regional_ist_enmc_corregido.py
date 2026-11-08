"""Paso 46: resumen regional y aportes al IST ENMC, sin rehacer geometrías."""
from pathlib import Path
import pandas as pd
import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports' / 'enmc'
REPORT.mkdir(parents=True, exist_ok=True)
DATA = pd.read_csv(REPORT / '43_ist_enmc.csv')
if len(DATA) != 347 or DATA.duplicated(['fuente', 'id_fuente']).any():
    raise ValueError('Se esperaban 347 unidades con clave fuente/id_fuente única.')

# OA: conservar las etiquetas regionales del propio inventario OA.
oapath = ROOT / 'OA-2-Articulo.shp'
oa = gpd.read_file(oapath, engine='pyogrio', ignore_geometry=True)
for required in ['OBJECTID', 'REGION']:
    if required not in oa:
        raise ValueError(f'Falta {required} en {oapath}')
if oa['OBJECTID'].duplicated().any():
    raise ValueError('OBJECTID duplicado en fuente OA')

oa_region = oa[['OBJECTID', 'REGION']].rename(columns={'OBJECTID':'id_fuente','REGION':'region'})
oa_region['id_fuente'] = pd.to_numeric(oa_region['id_fuente'], errors='raise')

o = DATA[DATA['fuente'] == 'OA_ENMC'].copy()
o = o.merge(oa_region, on='id_fuente', how='left', validate='one_to_one')

# COCHILCO: asignación geográfica por intersección de puntos con regiones.
p = DATA[DATA['fuente'] == 'COCHILCO_ENMC'].copy()
projects_path = ROOT / 'data/processed/enmc/cochilco_enmc_proyectos.gpkg'
regions_path = ROOT / 'data/processed/regiones_consolidadas.gpkg'
projects = gpd.read_file(projects_path, engine='pyogrio')
regions = gpd.read_file(regions_path, engine='pyogrio')
print('Campos proyectos:', list(projects.columns), flush=True)
print('Campos regiones:', list(regions.columns), flush=True)

if projects.crs is None or regions.crs is None:
    raise ValueError('Los proyectos y regiones necesitan CRS válido')

# Paso 43 generó id_calculo=1..55 por orden de lectura del mismo GPKG.
# Reproducimos esa clave y verificamos nombre-a-nombre ANTES del cruce espacial.
import unicodedata

def canon(value):
    txt = unicodedata.normalize('NFKD', str(value).strip().casefold())
    return ' '.join(''.join(ch for ch in txt if not unicodedata.combining(ch)).split())

if len(projects) != 55:
    raise ValueError(f'Esperábamos 55 proyectos, encontramos {len(projects)}')
if projects['geometry'].isna().any() or projects.geometry.is_empty.any():
    raise ValueError('Hay geometrías vacías en proyectos COCHILCO')
if 'proyecto' not in projects.columns:
    raise ValueError('El GeoPackage no contiene la columna proyecto')

projects = projects.reset_index(drop=True).copy()
projects['id_fuente'] = range(1, len(projects) + 1)
p['id_fuente'] = pd.to_numeric(p['id_fuente'], errors='raise').astype('int64')
check = p[['id_fuente','nombre']].merge(
    projects[['id_fuente','proyecto']], on='id_fuente', how='outer',
    validate='one_to_one', indicator=True)
if (check['_merge'] != 'both').any():
    raise ValueError('No coinciden las 55 claves entre el paso 43 y el GeoPackage')
bad = check.loc[check.apply(lambda row: canon(row['nombre']) != canon(row['proyecto']), axis=1)]
if len(bad):
    print(bad.head(15).to_string(index=False))
    raise ValueError('El orden o los nombres de COCHILCO cambiaron; no es seguro regionalizar')
print('Correspondencia COCHILCO verificada: 55/55 claves y nombres', flush=True)
id_col = 'id_fuente'

preferred = ['REGION', 'NOM_REG', 'NOMBRE_REG', 'NOM_REGION', 'NOMBRE', 'region', 'nom_reg']
name_candidates = [c for c in preferred if c in regions.columns and c != 'geometry']
if not name_candidates:
    name_candidates = [c for c in regions.columns if c != 'geometry' and regions[c].dtype == 'object']
if not name_candidates:
    raise ValueError('No se encontró campo de nombre regional')
name_col = name_candidates[0]
print(f'Clave COCHILCO: {id_col}; nombre región: {name_col}', flush=True)

geos = projects[[id_col, 'geometry']].rename(columns={id_col:'id_fuente'}).to_crs(regions.crs)
reg = regions[[name_col, 'geometry']].rename(columns={name_col:'region'})
matched = gpd.sjoin(geos, reg, how='left', predicate='intersects')
# Una coincidencia única por proyecto; si no, reportar sin inventar la región.
if matched['id_fuente'].duplicated().any():
    duplicates = matched.loc[matched['id_fuente'].duplicated(False), 'id_fuente'].tolist()
    raise ValueError(f'Proyectos con más de una intersección regional: {duplicates}')
match_table = pd.DataFrame(matched[['id_fuente', 'region']])
p = p.merge(match_table, on='id_fuente', how='left', validate='one_to_one')

all_units = pd.concat([o, p], ignore_index=True)
all_units['region'] = all_units['region'].fillna('SIN_REGION').astype(str).str.strip()
print('Sin región OA:', (o['region'].isna()).sum())
print('Sin región COCHILCO:', (p['region'].isna()).sum())

region_summary = (all_units.groupby(['fuente','region'], dropna=False)['IST_100']
    .agg(n='count', media='mean', mediana='median', minimo='min', maximo='max')
    .reset_index().sort_values(['fuente','media'], ascending=[True,False]))
region_summary.to_csv(REPORT / '46_ist_por_region.csv', index=False, encoding='utf-8-sig')

components = ['AP','SB','GL','HU','AI','CI','AD','PO','TU']
contrib = all_units.groupby('fuente')[[f'A_{k}' for k in components]].mean().reset_index()
contrib.to_csv(REPORT / '46_aportes_promedio_ist.csv', index=False, encoding='utf-8-sig')
all_units[['fuente','id_fuente','nombre','region','IST_100']].to_csv(
    REPORT / '46_unidades_ist_regionalizadas.csv',index=False,encoding='utf-8-sig')

print('\n=== RESUMEN REGIONAL ===')
print(region_summary.to_string(index=False))
print('\n=== APORTE PROMEDIO POR FUENTE ===')
print(contrib.to_string(index=False))
print('\nPASO 46 FINALIZADO')
