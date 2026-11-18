#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 69d: auditar sin reasignar el punto OA no contenido en regiones."""
from pathlib import Path
import json
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from shapely.ops import transform
from pyproj import CRS, Transformer

ROOT = Path(__file__).resolve().parents[1]
OA = ROOT / 'data/processed/enmc/oa_enmc_candidatas.gpkg'
REGIONS = ROOT / 'data/processed/regiones_consolidadas.gpkg'
COMMUNES = ROOT / 'data/processed/comunas_consolidadas.gpkg'
REPORTS = ROOT / 'reports/enmc'
SOURCE_ID = '162'
CRS_AREA = 'EPSG:6933'

def local_distance_m(point, geometry):
    lonlat = gpd.GeoSeries([point], crs=CRS_AREA).to_crs('EPSG:4326').iloc[0]
    aeqd = CRS.from_proj4(f'+proj=aeqd +lat_0={lonlat.y} +lon_0={lonlat.x} +datum=WGS84 +units=m +no_defs')
    proj = Transformer.from_crs(CRS_AREA, aeqd, always_xy=True).transform
    return float(transform(proj, point).distance(transform(proj, geometry)))

def main():
    REPORTS.mkdir(parents=True, exist_ok=True)
    oa = gpd.read_file(OA, engine='pyogrio').to_crs(CRS_AREA)
    if 'OBJECTID' not in oa.columns:
        raise ValueError('No existe OBJECTID en OA')
    candidate = oa.loc[oa.OBJECTID.astype(str) == SOURCE_ID]
    if len(candidate) != 1:
        raise ValueError(f'OBJECTID {SOURCE_ID}: registros encontrados={len(candidate)}, se esperaba 1')
    poly = candidate.geometry.iloc[0]
    if poly is None or poly.is_empty:
        raise ValueError('OA sin geometria')
    point = poly.representative_point()
    regions = gpd.read_file(REGIONS, engine='pyogrio').to_crs(CRS_AREA)
    if 'nomreg' not in regions.columns:
        raise ValueError('Falta nomreg en regiones')
    records = []
    for row in regions.itertuples(index=False):
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        records.append({
            'region':str(row.nomreg),
            'punto_intersecta': bool(point.intersects(geom)),
            'poligono_oa_intersecta': bool(poly.intersects(geom)),
            'distancia_punto_m': local_distance_m(point,geom),
            'distancia_poligono_m': local_distance_m(poly,geom),
        })
    df = pd.DataFrame(records).sort_values('distancia_punto_m')
    df.to_csv(REPORTS/'69d_distancias_regionales_oa_162.csv', index=False, encoding='utf-8-sig')
    ptll = gpd.GeoSeries([point], crs=CRS_AREA).to_crs('EPSG:4326').iloc[0]
    original_attributes = {}
    for key, value in candidate.drop(columns='geometry').iloc[0].items():
        if pd.isna(value):
            continue
        if any(s in key.lower() for s in ('reg','com','nom','nombre','tipo','estado')):
            original_attributes[key] = str(value)
    commune_result = []
    if COMMUNES.exists():
        communes = gpd.read_file(COMMUNES,engine='pyogrio').to_crs(CRS_AREA)
        hit = communes.loc[communes.geometry.intersects(point)]
        if len(hit):
            commune_result = [str(x) for x in hit.drop(columns='geometry').head(3).to_dict('records')]
    control = {
        'fuente':'OA_ENMC', 'OBJECTID':SOURCE_ID,
        'criterio_punto':'representative_point() del poligono OA en EPSG:6933',
        'lat':float(ptll.y),'lon':float(ptll.x),
        'area_original_ha': float(poly.area/10000),
        'punto_intersecta_alguna_region':bool(df.punto_intersecta.any()),
        'poligono_original_intersecta_alguna_region':bool(df.poligono_oa_intersecta.any()),
        'regiones_mas_cercanas':df.head(3).to_dict('records'),
        'atributos_originales_relevantes':original_attributes,
        'comunas_que_contienen_punto':commune_result,
        'advertencia':'Diagnostico, no reasigna la region ni modifica el IST.'
    }
    (REPORTS/'69d_diagnostico_oa_162.json').write_text(json.dumps(control, indent=2, ensure_ascii=False), encoding='utf-8')
    print('=== PASO 69d: DIAGNOSTICO DE UNIDAD OA SIN REGION ===')
    print(f'OBJECTID={SOURCE_ID} | lat={ptll.y:.7f} lon={ptll.x:.7f} | area OA={poly.area/10000:,.2f} ha')
    print('Regiones cercanas:')
    print(df.head(4).to_string(index=False, float_format=lambda x:f'{x:.2f}'))
    print('Poligono OA intersecta alguna region:', bool(df.poligono_oa_intersecta.any()))
    print('Punto OA intersecta alguna region:', bool(df.punto_intersecta.any()))
    print('Atributos administrativos originales:', original_attributes)
    print('Salidas: reports/enmc/69d_distancias_regionales_oa_162.csv y 69d_diagnostico_oa_162.json')
    print('PASO 69d FINALIZADO')

if __name__ == '__main__':
    main()
