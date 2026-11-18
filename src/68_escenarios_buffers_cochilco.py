#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 68: escenarios territoriales hipotéticos para COCHILCO (10/25/50/100 km).

NO SON huellas de proyecto ni superficie de intervención. Cada círculo se
construye en AEQD centrada en el punto de fuente y luego se lleva a EPSG:6933.
Resultados: geopackages locales ignorados por Git, resúmenes CSV publicables.
El área es la de los círculos completos: NO está recortada por Chile/343 comunas.

Uso: python -u src/68_escenarios_buffers_cochilco.py
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime,timezone
import json
import math
import geopandas as gpd
import pandas as pd
import shapely
from shapely.ops import transform
from pyproj import CRS,Transformer

ROOT=Path(__file__).resolve().parents[1]
COCH=ROOT/'data/processed/enmc/cochilco_enmc_proyectos.gpkg'
OUT=ROOT/'data/processed/enmc/escenarios_buffers'
REPORT=ROOT/'reports/enmc'
AREA='EPSG:6933'
RADII=(10,25,50,100)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    REPORT.mkdir(parents=True,exist_ok=True)
    if not COCH.exists(): raise FileNotFoundError(COCH)
    points=gpd.read_file(COCH,engine='pyogrio')
    if points.crs is None or len(points)!=55: raise RuntimeError('Se esperan 55 proyectos con CRS')
    points=points.to_crs('EPSG:4326')
    if not points.geom_type.eq('Point').all(): raise RuntimeError('COCHILCO requiere geometrías Point')
    idc=next((x for x in ('id_proyecto','ID_PROY','ID','OBJECTID') if x in points),None)
    if idc is None: points['id_calculo']=range(1,len(points)+1);idc='id_calculo'
    namec=next((x for x in ('NOMBRE','nombre','PROYECTO','proyecto') if x in points),None)
    if namec is None: raise RuntimeError('Sin campo nombre COCHILCO')
    print('=== PASO 68: ESCENARIOS BUFFERS HIPOTETICOS ===',flush=True)
    summaries=[]
    for km in RADII:
        rows=[]
        for _,r in points.iterrows():
            p=r.geometry
            local=CRS.from_proj4(f'+proj=aeqd +lat_0={p.y:.10f} +lon_0={p.x:.10f} +datum=WGS84 +units=m +no_defs')
            fwd=Transformer.from_crs('EPSG:4326',local,always_xy=True).transform
            back=Transformer.from_crs(local,AREA,always_xy=True).transform
            center=transform(fwd,p)
            ring=center.buffer(km*1000,quad_segs=32)
            geom=transform(back,ring)
            rows.append({'id_fuente':str(r[idc]),'proyecto':str(r[namec]),'radio_km':km,
                         'area_ha_circulo':geom.area/10000,'geometry':geom})
        g=gpd.GeoDataFrame(rows,geometry='geometry',crs=AREA)
        if g.geometry.isna().any() or not g.geometry.is_valid.all():
            raise RuntimeError(f'Geometrías de buffer inválidas: {km} km')
        geo=OUT/f'68_buffers_{km}km.gpkg'
        if geo.exists(): geo.unlink()
        g.to_file(geo,driver='GPKG',engine='pyogrio')
        # Unión explícita para descontar superposiciones (sin recorte territorial).
        unique=shapely.union_all(g.geometry.to_numpy())
        area_unique=unique.area/10000
        sum_ind=float(g.area.sum()/10000)
        overlap=sum_ind-area_unique
        if overlap < -1e-4: raise RuntimeError('Error de balance geométrico')
        summaries.append({'radio_km':km,'n_proyectos':55,
            'suma_areas_circulos_ha':sum_ind,'area_union_sin_duplicacion_ha':area_unique,
            'area_solapada_por_recuento_ha':max(overlap,0),
            'porcentaje_recuento_duplicado':100*max(overlap,0)/sum_ind,
            'alcance':'CIRCULOS_COMPLETOS_SIN_RECORTE_TERRITORIAL',
            'interpretacion':'ESCENARIO_ANALITICO_NO_HUELLA_MINERA'})
        print(f'  {km:3} km | unión={area_unique:,.1f} ha | suma={sum_ind:,.1f} ha | duplicación={100*overlap/sum_ind:.2f}%',flush=True)
    out=REPORT/'68_escenarios_buffers_cochilco.csv'
    pd.DataFrame(summaries).to_csv(out,index=False,encoding='utf-8-sig')
    meta={'fecha_utc':datetime.now(timezone.utc).isoformat(),'radios_km':RADII,
          'unidades':55,'metodo':'buffer métrico local AEQD, área medida EPSG:6933',
          'scope':'círculos completos, no recortados por área de estudio',
          'interpretacion':'escenarios de proximidad territorial, nunca huellas verificadas ni derechos concesionales',
          'nota':'No utilizar los buffers para reemplazar la geometría puntual del IST homologado.'}
    (REPORT/'68_control_buffers_cochilco.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False),encoding='utf-8')
    print('Archivos:',out,OUT,flush=True)
    print('PASO 68 FINALIZADO',flush=True)

if __name__=='__main__':main()
