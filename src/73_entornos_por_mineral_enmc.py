#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 73: escenarios territoriales de los 55 proyectos ENMC por mineral.

Uso:
 python -u src/73_entornos_por_mineral_enmc.py --radius 10
 python -u src/73_entornos_por_mineral_enmc.py --resume

Cruza buffers completos del paso 68 con la UNION del ámbito 343 comunas y
la UNION de concesiones constituidas. La unión por mineral/radio elimina
la duplicación entre los proyectos de ese grupo. NO son huellas mineras,
NO atribuyen el mineral a concesiones y NO miden impacto ambiental.

Archivos: reports/enmc/73_escenarios_por_mineral_ambito.csv,
73_control_escenarios_por_mineral.json, figura PNG.
"""
from __future__ import annotations
import argparse
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import GeometryCollection

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/enmc'
OUTFIG=ROOT/'outputs/figures/enmc'
GEODIR=ROOT/'data/processed/enmc/escenarios_buffers'
CRS='EPSG:6933'
RADII=(10,25,50,100)
COLS=('radio_km','mineral','n_proyectos','superficie_buffer_completo_suma_ha',
      'superficie_buffer_completo_union_ha','superficie_buffer_en_ambito_ha',
      'superficie_concesion_en_entorno_ha','porcentaje_entorno_concesionado',
      'porcentaje_buffer_union_dentro_ambito','estado')

def canonical(v):
    v=unicodedata.normalize('NFKD',str(v).casefold())
    return re.sub('[^a-z0-9]+','', ''.join(c for c in v if not unicodedata.combining(c)))

def clean(g):
    if g is None or g.is_empty: return GeometryCollection()
    if not g.is_valid:g=shapely.make_valid(g)
    if g.geom_type in ('Polygon','MultiPolygon'):return g
    parts=[p for p in shapely.get_parts(g) if p.geom_type in ('Polygon','MultiPolygon') and not p.is_empty]
    return shapely.union_all(parts) if parts else GeometryCollection()

def load_geo(path):
    if not path.is_file():raise FileNotFoundError(path)
    g=gpd.read_file(path,engine='pyogrio')
    if g.crs is None:raise ValueError(f'Sin CRS: {path}')
    return g.to_crs(CRS)

def add_outputs(df,scope,report):
    report.mkdir(parents=True,exist_ok=True)
    target=report/'73_escenarios_por_mineral_ambito.csv'
    temp=target.with_suffix('.new.csv')
    df.to_csv(temp,index=False,encoding='utf-8-sig',float_format='%.8f')
    temp.replace(target)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--radius',type=int,choices=RADII,help='Probar solo un radio')
    parser.add_argument('--resume',action='store_true',help='Continuar sin repetir combinaciones ya guardadas')
    args=parser.parse_args()
    REPORT.mkdir(parents=True,exist_ok=True);OUTFIG.mkdir(parents=True,exist_ok=True)
    print('=== PASO 73: ENTORNOS TERRITORIALES POR MINERAL ===',flush=True)
    ctl=REPORT/'72_control_analisis_mineral.json'
    if not ctl.is_file() or json.loads(ctl.read_text(encoding='utf-8'))['estado']!='VALIDADO':
        raise RuntimeError('El paso 72 debe estar VALIDADO antes del análisis territorial')
    labels=pd.read_csv(REPORT/'72_matriz_proyecto_mineral_region_componentes.csv',encoding='utf-8-sig',dtype={'id_fuente':'string'})
    needed={'id_fuente','proyecto','mineral'}
    if not needed.issubset(labels.columns):raise ValueError(f'Faltan columnas: {needed-set(labels.columns)}')
    if labels.id_fuente.nunique()!=55 or labels[['id_fuente','mineral']].duplicated().any():
        raise ValueError('La tabla mineral debe tener 55 IDs únicos y sin pares repetidos')
    byname=dict(zip(labels.proyecto.map(canonical),labels.id_fuente.astype(str)))
    if len(byname)!=55:raise ValueError('Proyectos no tienen nombres únicos normalizados')
    attr=labels[['id_fuente','mineral']].drop_duplicates().copy()
    communes=load_geo(ROOT/'data/processed/comunas_consolidadas.gpkg')
    if len(communes)!=343:raise ValueError('El ámbito debe contener exactamente 343 comunas')
    scope=clean(shapely.union_all([clean(g) for g in communes.geometry]))
    concessions=load_geo(ROOT/'data/processed/enmc/35_concesiones_constituidas_ambito.gpkg')
    if len(concessions)!=1:raise ValueError('Concesiones deben tener una sola geometría unida')
    con=clean(concessions.geometry.iloc[0].intersection(scope))
    print(f'Ámbito 343 comunas={scope.area/1e4:,.2f} ha; concesiones={con.area/1e4:,.2f} ha',flush=True)
    path=REPORT/'73_escenarios_por_mineral_ambito.csv'
    old=pd.read_csv(path,encoding='utf-8-sig') if args.resume and path.exists() else pd.DataFrame(columns=COLS)
    if not old.empty and not set(COLS).issubset(old.columns):raise ValueError('CSV existente con esquema incompatible')
    found={(int(r.radio_km),str(r.mineral)) for r in old.itertuples()}
    items=old.to_dict('records')
    radii=(args.radius,) if args.radius else RADII
    for km in radii:
        geo=load_geo(GEODIR/f'68_buffers_{km}km.gpkg')
        if len(geo)!=55 or not geo.geom_type.isin(['Polygon','MultiPolygon']).all():
            raise ValueError(f'Buffer {km} km: esperado 55 polígonos')
        if 'id_fuente' not in geo or 'proyecto' not in geo:raise ValueError('GPKG sin identificador o nombre')
        geo['id_fuente']=geo.id_fuente.astype(str)
        # Control cruzado por NOMBRE, no confiar en IDs coincidentes por casualidad.
        keys=geo.proyecto.map(canonical)
        if keys.duplicated().any() or set(keys)!=set(byname):
            raise ValueError(f'Los nombres del paso 68 no coinciden 1:1 con paso 72: {km} km')
        geo['_id_auditado']=keys.map(byname)
        if geo['_id_auditado'].isna().any():raise ValueError('Error de correspondencia de proyecto')
        joint=geo[['_id_auditado','geometry']].merge(attr,left_on='_id_auditado',right_on='id_fuente',how='inner',validate='one_to_many')
        if joint['_id_auditado'].nunique()!=55:raise ValueError('No se preservan los 55 proyectos')
        for mineral,sub in joint.groupby('mineral',sort=True):
            if (km,str(mineral)) in found:
                print(f'  {km} km / {mineral}: existente',flush=True);continue
            n=int(sub['_id_auditado'].nunique())
            circle_sum=float(sub.geometry.area.sum()/1e4)
            united=clean(shapely.union_all(sub.geometry.to_numpy()))
            whole=float(united.area/1e4)
            in_scope=clean(united.intersection(scope))
            in_area=float(in_scope.area/1e4)
            coincide=clean(in_scope.intersection(con))
            con_area=float(coincide.area/1e4)
            if con_area>in_area+1e-4 or in_area>whole+1e-4:
                raise ValueError(f'Balance incorrecto {km}/{mineral}')
            if circle_sum+1e-4<whole:raise ValueError('Suma de círculos menor que unión')
            items.append({'radio_km':km,'mineral':mineral,'n_proyectos':n,
                          'superficie_buffer_completo_suma_ha':circle_sum,
                          'superficie_buffer_completo_union_ha':whole,
                          'superficie_buffer_en_ambito_ha':in_area,
                          'superficie_concesion_en_entorno_ha':con_area,
                          'porcentaje_entorno_concesionado':100*con_area/in_area if in_area else np.nan,
                          'porcentaje_buffer_union_dentro_ambito':100*in_area/whole if whole else np.nan,
                          'estado':'ESCENARIO_NO_HUELLA_NO_ATRIBUCION_MINERAL_A_CONCESIONES'})
            df=pd.DataFrame(items,columns=COLS).sort_values(['radio_km','mineral'])
            add_outputs(df,scope,REPORT)
            print(f'  {km:3} km / {mineral:14s}: n={n:2d} | ámbito={in_area:,.1f} ha | concesión={con_area:,.1f} ha ({100*con_area/in_area if in_area else float("nan"):.2f}%)',flush=True)
    result=pd.DataFrame(items,columns=COLS).sort_values(['radio_km','mineral'])
    unique=result[['radio_km','mineral']].drop_duplicates()
    target=24 if args.radius is None else 6
    complete=len(unique)==target
    control={'fecha_utc':datetime.now(timezone.utc).isoformat(),
             'estado':'PRUEBA_RADIO' if args.radius is not None else ('COMPLETO' if complete else 'PARCIAL'),
             'combinaciones_calculadas':int(len(unique)), 'combinaciones_objetivo':target,
             'n_proyectos_fuente':55, 'n_minerales':6,
             'ambito':'343 comunas, unión de geometrías, EPSG:6933',
             'metodo':'unión de buffers por mineral/radio recortada a las 343 comunas; coincidencia con unión concesional',
             'limites':['buffers son escenarios hipotéticos, no huellas de proyectos',
                        'concesiones no tienen mineral; la coincidencia se asocia al entorno de proyectos del mineral, NO a concesiones del mineral',
                        'un mismo proyecto puede aparecer en varios minerales si es multiminérico',
                        'coberturas de diferentes minerales pueden superponerse y no deben sumarse',
                        'radios no fueron justificados por evidencia de alcance de impacto']}
    (REPORT/'73_control_escenarios_por_mineral.json').write_text(json.dumps(control,ensure_ascii=False,indent=2),encoding='utf-8')
    if complete and args.radius is None:
        fig,ax=plt.subplots(figsize=(10,5.5))
        for mineral,part in result.groupby('mineral'):
            ax.plot(part.radio_km,part.superficie_buffer_en_ambito_ha/1e6,marker='o',label=f'{mineral} (n={int(part.n_proyectos.iloc[0])})')
        ax.set_xlabel('Radio del entorno hipotético (km)')
        ax.set_ylabel('Superficie única dentro del ámbito (millones ha)')
        ax.set_title('Entornos territoriales de proyectos por mineral — escenarios, no huellas')
        ax.set_xticks(RADII)
        ax.legend(loc='upper left',fontsize=8,ncol=2)
        fig.tight_layout()
        fig.savefig(OUTFIG/'73_entornos_por_mineral_radios.png',dpi=180)
        plt.close(fig)
        print('Figura: outputs/figures/enmc/73_entornos_por_mineral_radios.png',flush=True)
    print(f'Estado={control["estado"]}; combinaciones={len(unique)}/{target}',flush=True)
    print('PASO 73 FINALIZADO',flush=True)

if __name__=='__main__':main()
