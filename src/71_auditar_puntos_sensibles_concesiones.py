#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 71: auditoria puntual de comunidades indigenas y atractivos turisticos.

No reemplaza ni modifica las hectareas del paso 70. Para cada registro de tipo
Point o MultiPoint, determina pertenencia al ambito (343 comunas), coincidencia
con la union de concesiones constituidas y asignacion regional geometrica.
Los registros no puntuales se contabilizan como excluidos de este indicador.

Uso:
    python -u src/71_auditar_puntos_sensibles_concesiones.py
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
import geopandas as gpd
import pandas as pd
import shapely
from shapely.prepared import prep

EPSG = 'EPSG:6933'
LAYERS = {'CI':'39_comunidades_indigenas.gpkg',
          'AT':'39_atractivos_turisticos.gpkg'}

def load(path: Path) -> gpd.GeoDataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    gdf = gpd.read_file(path, engine='pyogrio')
    if gdf.crs is None:
        raise ValueError(f'Sin CRS: {path}')
    return gdf.to_crs(EPSG)

def repaired_polygon(geoms):
    parts=[]
    for geom in geoms:
        if geom is None or geom.is_empty: continue
        g=geom if geom.is_valid else shapely.make_valid(geom)
        if g.geom_type in ('Polygon','MultiPolygon'): parts.append(g)
        else:
            parts.extend(p for p in shapely.get_parts(g)
                         if p.geom_type in ('Polygon','MultiPolygon') and not p.is_empty)
    if not parts: raise ValueError('Union de poligonos vacia')
    return shapely.union_all(parts)

def is_point_geometry(g):
    return g is not None and not g.is_empty and g.geom_type in ('Point','MultiPoint')

def main():
    root=Path(__file__).resolve().parents[1]
    out=root/'reports/enmc'
    out.mkdir(parents=True,exist_ok=True)
    print('=== PASO 71: INDICADORES PUNTUALES COMPLEMENTARIOS ===',flush=True)
    communes=load(root/'data/processed/comunas_consolidadas.gpkg')
    regions=load(root/'data/processed/regiones_consolidadas.gpkg')
    concession=load(root/'data/processed/enmc/35_concesiones_constituidas_ambito.gpkg')
    if len(communes)!=343 or len(regions)!=16 or len(concession)!=1:
        raise ValueError('Universo de comunas/regiones/concesion diferente al esperado')
    if 'nomreg' not in regions.columns:
        raise ValueError('Falta campo nomreg en regiones')
    area=repaired_polygon(communes.geometry)
    rights=repaired_polygon(concession.geometry)
    inside_area=prep(area)
    inside_rights=prep(rights)
    region_shapes=[(str(r['nomreg']), prep(r.geometry)) for _,r in regions.iterrows()]
    points=[]
    summary=[]
    anomalies=[]
    for code,filename in LAYERS.items():
        src=load(root/'data/processed/enmc/sensibilidad'/filename)
        types=src.geometry.geom_type.value_counts(dropna=False).to_dict()
        counts={'total_fuente':len(src),'tipos_geometricos':{str(k):int(v) for k,v in types.items()},
                'sin_geometria':0,'no_puntuales':0,'fuera_ambito':0,
                'puntos_en_ambito':0,'coincidentes_concesion':0,'sin_region':0,'multiregion':0}
        print(f'{code}: fuente={len(src)} | geometria={counts["tipos_geometricos"]}',flush=True)
        for i,g in enumerate(src.geometry):
            if g is None or g.is_empty:
                counts['sin_geometria']+=1
                continue
            if not is_point_geometry(g):
                counts['no_puntuales']+=1
                continue
            # Un registro multipunto se cuenta una sola vez; debe tener al menos
            # un punto en ambito. La coincidencia exige punto dentro de concesion.
            pointparts=[g] if g.geom_type=='Point' else list(shapely.get_parts(g))
            inparts=[p for p in pointparts if inside_area.covers(p)]
            if not inparts:
                counts['fuera_ambito']+=1
                continue
            counts['puntos_en_ambito']+=1
            hit=any(inside_rights.covers(p) for p in inparts)
            if hit:counts['coincidentes_concesion']+=1
            assigned=[name for name,poly in region_shapes
                      if any(poly.covers(p) for p in inparts)]
            assigned=list(dict.fromkeys(assigned))
            if len(assigned)==0:counts['sin_region']+=1
            if len(assigned)>1:counts['multiregion']+=1
            region=assigned[0] if len(assigned)==1 else 'SIN_REGION' if not assigned else 'MULTIRREGION'
            row={'componente':code,'indice_fuente':i,'region':region,
                 'coincide_concesion':int(hit),'tipo_geometria':g.geom_type,
                 'n_puntos_geometria':len(pointparts),'n_puntos_en_ambito':len(inparts)}
            points.append(row)
            if len(assigned)!=1:anomalies.append(row)
        n=counts['puntos_en_ambito'];hits=counts['coincidentes_concesion']
        counts['porcentaje_registros_en_concesion']=(100*hits/n if n else None)
        summary.append({'componente':code,**counts})
        print(f'  Ambito: {n:,}; en concesiones: {hits:,}; '
              f'porcentaje registros: {counts["porcentaje_registros_en_concesion"]}',flush=True)
        print(f'  Sin region: {counts["sin_region"]}; multirregion: {counts["multiregion"]}',flush=True)
    df=pd.DataFrame(points)
    if df.empty:raise ValueError('No se encontraron registros puntuales en el ambito')
    regional=(df.groupby(['componente','region'],dropna=False)
              .agg(n_registros=('indice_fuente','size'),
                   n_coincidentes=('coincide_concesion','sum'))
              .reset_index())
    regional['porcentaje_registros_coincidentes']=100*regional.n_coincidentes/regional.n_registros
    for code in LAYERS:
        s=next(x for x in summary if x['componente']==code)
        r=regional[regional.componente==code]
        assert int(r.n_registros.sum())==s['puntos_en_ambito']
        assert int(r.n_coincidentes.sum())==s['coincidentes_concesion']
    df.to_csv(out/'71_registros_puntuales_individuales.csv',index=False,encoding='utf-8-sig')
    regional.to_csv(out/'71_puntos_sensibles_coincidencia_regional.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(anomalies).to_csv(out/'71_puntos_sin_region_o_multirregion.csv',index=False,encoding='utf-8-sig')
    meta={'generado_utc':datetime.now(timezone.utc).isoformat(),
          'fuentes':LAYERS,'resumen':summary,
          'metodologia':'Registros puntuales originales en ambito de 343 comunas; coincidencia del punto con union de concesiones, sin buffers. MultiPoint se cuenta por registro, con coincidencia si algun punto esta en concesion. No son superficies de afectacion ni impactos.',
          'advertencia':'No comparar porcentaje de registros puntuales con porcentajes de superficie del paso 70. La calidad y representatividad geografica de cada registro no ha sido validada individualmente.'}
    (out/'71_control_puntos_sensibles.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Reportes: 71_puntos_sensibles_coincidencia_regional.csv, 71_registros_puntuales_individuales.csv, 71_control_puntos_sensibles.json',flush=True)
    print('PASO 71 FINALIZADO',flush=True)

if __name__=='__main__':main()
