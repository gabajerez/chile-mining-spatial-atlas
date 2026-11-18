#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 70: coincidencias regionales entre concesiones constituidas y 9 componentes IST.

Universo: intersección de las 343 comunas consolidadas con las regiones.
Denominador: superficie única de cada componente dentro de cada región (ha).
Numerador: intersección de esa superficie con la UNIÓN de concesiones constituidas.
No identifica mineral ni impacto. Superposiciones entre componentes NO se suman.

Ejemplo (primero probar una región y un componente):
    python -u src/70_overlap_regional_componentes_enmc.py --region atacama --component HU
    python -u src/70_overlap_regional_componentes_enmc.py --resume

Guardado incremental: reports/enmc/70_overlap_regional_componentes_checkpoint.csv.
"""
from __future__ import annotations
import argparse
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import GeometryCollection

CRS = 'EPSG:6933'
LAYERS = {
    'AP': ('areas_protegidas',),
    'SB': ('sitios_prioritarios', 'reservas_biosfera'),
    'GL': ('glaciares',),
    'HU': ('humedales_mma_nacional',),
    'AI': ('planes_atmosfericos',),
    'CI': ('comunidades_indigenas',),
    'AD': ('areas_desarrollo_indigena',),
    'PO': ('areas_pobladas',),
    'TU': ('atractivos_turisticos', 'zonas_interes_turistico'),
}
NAMES = {'AP':'Areas protegidas','SB':'Sitios prioritarios + reservas biosfera',
         'GL':'Glaciares','HU':'Humedales MMA nacional','AI':'Planes atmosfericos',
         'CI':'Comunidades indigenas','AD':'Areas desarrollo indigena',
         'PO':'Areas pobladas','TU':'Atractivos + zonas interes turistico'}
COLUMNS = ['region','componente','nombre_componente','n_geometrias_recortadas',
           'superficie_sensible_ha','superficie_coincidente_ha','superficie_no_coincidente_ha',
           'porcentaje_sensible_coincidente','error_balance_m2', 'denominador']

def norm(s):
    t=unicodedata.normalize('NFKD',str(s).lower())
    return re.sub(r'[^a-z0-9]','', ''.join(c for c in t if not unicodedata.combining(c)))

def area_poly(g):
    if g is None or g.is_empty:return GeometryCollection()
    if not g.is_valid:g=shapely.make_valid(g)
    if g.geom_type in ('Polygon','MultiPolygon'):return g
    pieces=[p for p in shapely.get_parts(g) if p.geom_type in ('Polygon','MultiPolygon') and not p.is_empty]
    return shapely.union_all(pieces) if pieces else GeometryCollection()

def checked_read(path, bbox=None):
    if not path.is_file():raise FileNotFoundError(path)
    kwargs={'engine':'pyogrio'}
    if bbox is not None:kwargs['bbox']=bbox
    frame=gpd.read_file(path,**kwargs)
    if frame.crs is None:raise ValueError(f'CRS ausente: {path}')
    return frame.to_crs(CRS)

def intersect_polys(frame, mask):
    pieces=[]
    if frame.empty:return pieces
    for g in frame.geometry:
        if g is None or g.is_empty:continue
        g=area_poly(g)
        if g.is_empty or not g.intersects(mask):continue
        v=area_poly(g.intersection(mask))
        if not v.is_empty:pieces.append(v)
    return pieces

def get_component(root,code,mask):
    all_parts=[]
    for key in LAYERS[code]:
        path=(root/'data/processed/enmc/sensibilidad'/
              ('56_humedales_mma_nacional.gpkg' if key=='humedales_mma_nacional' else f'39_{key}.gpkg'))
        frame=checked_read(path,bbox=mask.bounds)
        pieces=intersect_polys(frame,mask)
        print(f'    {key}: candidatos={len(frame)}, recortados={len(pieces)}',flush=True)
        all_parts.extend(pieces)
    if not all_parts:return GeometryCollection(),0
    return area_poly(shapely.union_all(all_parts)),len(all_parts)

def write_csv_atomic(path,records):
    df=pd.DataFrame(records,columns=COLUMNS)
    tmp=path.with_suffix('.temporary.csv')
    df.to_csv(tmp,index=False,encoding='utf-8-sig',float_format='%.9f')
    tmp.replace(path)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    ap.add_argument('--region',type=str,default=None,help='Texto del nombre regional; para prueba parcial')
    ap.add_argument('--component',choices=sorted(LAYERS),default=None,help='Codigo IST; para prueba parcial')
    ap.add_argument('--resume',action='store_true',help='Omitir combinaciones ya guardadas')
    args=ap.parse_args()
    root=args.root.resolve()
    reports=root/'reports/enmc';reports.mkdir(parents=True,exist_ok=True)
    cp=reports/'70_overlap_regional_componentes_checkpoint.csv'
    out=reports/'70_overlap_regional_componentes.csv'
    print('=== PASO 70: COINCIDENCIA CONCESIONAL POR REGION Y COMPONENTE ===',flush=True)
    regions=checked_read(root/'data/processed/regiones_consolidadas.gpkg')
    if len(regions)!=16 or 'nomreg' not in regions.columns:
        raise ValueError('Se esperan 16 regiones con nomreg')
    communes=checked_read(root/'data/processed/comunas_consolidadas.gpkg')
    if len(communes)!=343:raise ValueError(f'Se esperaban 343 comunas, hay {len(communes)}')
    commune_union=area_poly(shapely.union_all([area_poly(x) for x in communes.geometry]))
    print(f'Ambito unico 343 comunas: {commune_union.area/1e4:,.2f} ha',flush=True)
    c=checked_read(root/'data/processed/enmc/35_concesiones_constituidas_ambito.gpkg')
    if len(c)!=1:raise ValueError('Unión de concesiones no contiene una sola geometría')
    concess=area_poly(c.geometry.iloc[0]);del c
    if not concess.is_valid:raise ValueError('Concesiones invalidas')
    existing=[]
    if args.resume and cp.exists():
        existing=pd.read_csv(cp,encoding='utf-8-sig').to_dict('records')
        print(f'Reanudando {len(existing)} pares region-componente',flush=True)
    done={(str(r['region']),str(r['componente'])) for r in existing}
    records=list(existing)
    selected=0
    for _,r in regions.iterrows():
        region=str(r['nomreg'])
        if args.region and norm(args.region) not in norm(region):continue
        mask=area_poly(area_poly(r.geometry).intersection(commune_union))
        if mask.is_empty:
            print(f'  {region}: sin superficie en 343 comunas',flush=True)
            continue
        conreg=area_poly(concess.intersection(mask))
        print(f'-- {region}: ambito={mask.area/1e4:,.2f} ha, concesiones={conreg.area/1e4:,.2f} ha --',flush=True)
        for code in LAYERS:
            if args.component and code!=args.component:continue
            selected+=1
            if (region,code) in done:
                print(f'  {code}: existente, omitido',flush=True)
                continue
            layer,n=get_component(root,code,mask)
            sens=float(layer.area)/1e4
            intersect=area_poly(layer.intersection(conreg)) if not layer.is_empty else GeometryCollection()
            coincidence=float(intersect.area)/1e4
            outside=area_poly(layer.difference(conreg)) if not layer.is_empty else GeometryCollection()
            free=float(outside.area)/1e4
            error=abs(sens-coincidence-free)*1e4
            tol=max(1.0,layer.area*1e-8)
            if error>tol:
                raise ValueError(f'Balance invalido: {region}/{code}: {error:.4f} m² / tol {tol:.4f}')
            if coincidence>sens+0.0001:raise ValueError(f'Coincidencia excede cobertura: {region}/{code}')
            percent=100*coincidence/sens if sens>0 else np.nan
            records.append({'region':region,'componente':code,'nombre_componente':NAMES[code],
              'n_geometrias_recortadas':n,'superficie_sensible_ha':sens,
              'superficie_coincidente_ha':coincidence,'superficie_no_coincidente_ha':free,
              'porcentaje_sensible_coincidente':percent,'error_balance_m2':error,
              'denominador':'superficie de componente dentro de region y 343 comunas (union sin doble conteo)'})
            write_csv_atomic(cp,records)
            print(f'  {code}: sensible={sens:,.2f} ha, coincidencia={coincidence:,.2f} ha, porc={percent:.2f}% (guardado)',flush=True)
    df=pd.DataFrame(records,columns=COLUMNS)
    if df.duplicated(['region','componente']).any():raise ValueError('Pares region-componente duplicados')
    df=df.sort_values(['region','componente']).reset_index(drop=True)
    write_csv_atomic(out,df.to_dict('records'))
    expected=16*len(LAYERS)
    complete=len(df)==expected and set(df['region'])==set(regions['nomreg'].astype(str))
    control={'estado':'COMPLETO' if complete else 'PARCIAL','timestamp_utc':datetime.now(timezone.utc).isoformat(),
             'pares_esperados':expected,'pares_guardados':len(df),'pares_ejecutados_esta_vez':selected,
             'regiones':int(df.region.nunique()),'componentes':int(df.componente.nunique()),
             'ambito_comunas_ha':float(commune_union.area/1e4),
             'advertencia':'No sumar superficies de distintos componentes. Indicador descriptivo; sin atribucion mineral. Requiere contrastar agregados nacionales con fuentes previamente auditadas.'}
    if 'HU' in set(df.componente) and complete:
        wet=df[df.componente=='HU']
        control['humedales_suma_regional_ha']=float(wet.superficie_sensible_ha.sum())
        control['humedales_coincidencia_suma_regional_ha']=float(wet.superficie_coincidente_ha.sum())
        national=reports/'58_overlap_humedales_mma_resumen.csv'
        if national.exists():
            print('  Humedales paso 58: comparar 5,371,068.186 ha sensibles y 614,734.121 ha coincidentes',flush=True)
            print(f'  Paso 70 regional: {control["humedales_suma_regional_ha"]:,.3f} ha / {control["humedales_coincidencia_suma_regional_ha"]:,.3f} ha',flush=True)
    (reports/'70_control_overlap_regional.json').write_text(json.dumps(control,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Estado={control["estado"]}; pares={len(df)}/{expected}; archivo={out}',flush=True)
    if complete:
        national=df.groupby('componente',as_index=False).agg(sensible_ha=('superficie_sensible_ha','sum'),coincidente_ha=('superficie_coincidente_ha','sum'))
        national['porcentaje']=np.where(national.sensible_ha>0,100*national.coincidente_ha/national.sensible_ha,np.nan)
        nat=reports/'70_resumen_nacional_por_componente.csv'
        national.to_csv(nat,index=False,encoding='utf-8-sig')
        print(national.to_string(index=False),flush=True)
    print('PASO 70 FINALIZADO',flush=True)

if __name__=='__main__':main()
