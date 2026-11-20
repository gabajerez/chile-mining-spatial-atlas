#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 75: buffers circulares COCHILCO de area igual a mediana OA (292 huellas).
No modifica OA ni proyectos originales. Un buffer no representa huella futura real.
"""
from pathlib import Path
from datetime import datetime, timezone
import json, math
import geopandas as gpd
import numpy as np
from pyproj import CRS, Transformer
from shapely.geometry import Point, Polygon, MultiPolygon
from shapely.ops import transform, unary_union
import shapely

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/processed/enmc'; REPORT=ROOT/'reports/enmc'
OUT=BASE/'75_cochilco_buffers_mediana_oa.gpkg'
CRS_AREA='EPSG:6933'

def load(path):
    if not path.exists(): raise FileNotFoundError(path)
    df=gpd.read_file(path,engine='pyogrio')
    if df.crs is None: raise ValueError(f'CRS desconocido: {path}')
    return df.to_crs(CRS_AREA)

def main():
    REPORT.mkdir(parents=True,exist_ok=True)
    oa=load(BASE/'oa_enmc_candidatas.gpkg')
    if 'estado_oa_provisional' not in oa: raise KeyError('estado_oa_provisional')
    oa=oa.loc[oa.estado_oa_provisional.eq('CANDIDATA_OPERACION_POR_TIPO')].copy()
    if len(oa)!=292: raise ValueError(f'Esperadas 292 huellas OA, halladas {len(oa)}')
    if not oa.geom_type.isin(['Polygon','MultiPolygon']).all(): raise ValueError('OA contiene geometrías no poligonales')
    # Reparar únicamente geometrías inválidas, conservando exclusivamente componentes poligonales.
    # Nunca excluir unidades sin registrar el motivo ni cambiar silenciosamente el universo.
    if oa.geometry.isna().any() or oa.geometry.is_empty.any():
        raise ValueError('OA contiene geometrías nulas o vacías: auditar antes de continuar')
    invalid = oa.loc[~oa.geometry.is_valid].copy()
    print(f'Universo OA={len(oa)} | geometrías inválidas antes={len(invalid)}', flush=True)
    audit = []
    def polygonal_parts(g):
        if g.is_empty:
            return []
        if g.geom_type == 'Polygon':
            return [g]
        if g.geom_type == 'MultiPolygon':
            return list(g.geoms)
        if hasattr(g, 'geoms'):
            parts = []
            for sub in g.geoms:
                parts.extend(polygonal_parts(sub))
            return parts
        return []
    for idx, item in invalid.iterrows():
        before = item.geometry
        before_area = float(before.area)
        reason = str(shapely.is_valid_reason(before))
        fixed_raw = shapely.make_valid(before)
        parts = polygonal_parts(fixed_raw)
        if not parts:
            raise ValueError(f'OBJECTID={item.get("OBJECTID",idx)}: reparación sin polígonos')
        fixed = unary_union(parts) if len(parts) > 1 else parts[0]
        if fixed.is_empty or not fixed.is_valid or fixed.geom_type not in ('Polygon','MultiPolygon'):
            raise ValueError(f'OBJECTID={item.get("OBJECTID",idx)}: reparación inválida')
        after_area = float(fixed.area)
        delta_pct = 100.0 * (after_area - before_area) / before_area if before_area else float('inf')
        audit.append({'OBJECTID':str(item.get('OBJECTID',idx)),
                      'motivo_invalidez':reason,
                      'tipo_original':before.geom_type, 'tipo_reparado':fixed.geom_type,
                      'area_original_ha':before_area/1e4,
                      'area_reparada_ha':after_area/1e4,
                      'diferencia_ha':(after_area-before_area)/1e4,
                      'diferencia_pct':delta_pct})
        oa.at[idx, 'geometry'] = fixed
    # Auditar antes de admitir un cambio importante en el área de una huella.
    import pandas as pd
    audit_csv = REPORT/'75_auditoria_geometrias_oa.csv'
    pd.DataFrame(audit, columns=['OBJECTID','motivo_invalidez','tipo_original',
           'tipo_reparado','area_original_ha','area_reparada_ha',
           'diferencia_ha','diferencia_pct']).to_csv(audit_csv,index=False,encoding='utf-8-sig')
    if any(abs(a['diferencia_pct']) > 1.0 for a in audit):
        raise ValueError(f'Reparación altera más de 1% el área de alguna huella: revisar {audit_csv}')
    if not oa.geometry.is_valid.all() or not oa.geom_type.isin(['Polygon','MultiPolygon']).all():
        raise ValueError('Persisten geometrías no poligonales o inválidas después de reparar')
    areas=oa.geometry.area.to_numpy()/1e4
    if not np.isfinite(areas).all() or (areas<=0).any(): raise ValueError('Areas OA no positivas')
    median_ha=float(np.median(areas)); target=median_ha*1e4
    diameter_reference=2*math.sqrt(target/math.pi)
    coch=load(BASE/'cochilco_enmc_proyectos.gpkg')
    if len(coch)!=55 or not coch.geom_type.eq('Point').all():
        raise ValueError('COCHILCO: se esperan exactamente 55 puntos')
    ident=next((x for x in ('id_proyecto','ID_PROY','ID','OBJECTID') if x in coch),None)
    if ident is None:
        coch['id_calculo']=range(1,len(coch)+1);ident='id_calculo'
    if coch[ident].astype(str).duplicated().any(): raise ValueError('Identificadores COCHILCO duplicados')
    to_ll=Transformer.from_crs(CRS_AREA,'EPSG:4326',always_xy=True).transform
    rec=[]; geoms=[]
    for _,item in coch.iterrows():
        p=item.geometry; lonlat=transform(to_ll,p)
        local=CRS.from_proj4(f'+proj=aeqd +lat_0={lonlat.y:.12f} +lon_0={lonlat.x:.12f} +datum=WGS84 +units=m +no_defs')
        forward=Transformer.from_crs(CRS_AREA,local,always_xy=True).transform
        backward=Transformer.from_crs(local,CRS_AREA,always_xy=True).transform
        center=transform(forward,p)
        def circle(radius):
            # 256 segmentos para aproximación geométrica; ajustar area evaluada en EPSG:6933.
            return transform(backward,center.buffer(radius,quad_segs=64))
        low=0.;high=math.sqrt(target/math.pi)*1.2
        while circle(high).area<target: high*=1.25
        for _ in range(32):
            mid=(low+high)/2
            if circle(mid).area<target: low=mid
            else: high=mid
        radius=(low+high)/2; geom=circle(radius)
        error=geom.area-target
        if abs(error)>max(.02,target*1e-8):
            raise ValueError(f'Error area buffer > tolerancia: {error:.5f} m2')
        rec.append({'id_fuente':str(item[ident]),'area_oa_mediana_ha':median_ha,
                    'area_buffer_ha':geom.area/1e4,'radio_local_m':radius,
                    'diametro_local_m':2*radius,'diametro_referencia_m':diameter_reference,
                    'area_error_m2':error,'modo_geometria':'BUFFER_EQUIVALENTE_MEDIANA_OA'})
        geoms.append(geom)
    output=gpd.GeoDataFrame(rec,geometry=geoms,crs=CRS_AREA)
    if OUT.exists(): OUT.unlink()
    output.to_file(OUT,layer='buffers_mediana_oa',driver='GPKG',engine='pyogrio')
    output.drop(columns=['geometry']).to_csv(REPORT/'75_control_buffers_mediana_oa.csv',index=False,encoding='utf-8-sig')
    report={'estado':'COMPLETO','fecha_utc':datetime.now(timezone.utc).isoformat(),
            'universo_oa':292,'universo_proyectos':55,'geometrias_oa_reparadas':len(audit),'auditoria_reparaciones':str(audit_csv.relative_to(ROOT)).replace('\\','/'),'area_mediana_oa_ha':median_ha,
            'diametro_equivalente_teorico_m':diameter_reference,
            'rango_diametros_locales_m':[float(output.diametro_local_m.min()),float(output.diametro_local_m.max())],
            'desviacion_maxima_area_m2':float(output.area_error_m2.abs().max()),
            'crs_area':CRS_AREA,'metodo':'circulo AEQD local ajustado para area EPSG:6933',
            'limitacion':'Buffer analitico sin equivalencia comprobada con intervencion real; diametro local ajustado por proyeccion'}
    (REPORT/'75_control_buffers_mediana_oa.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print('=== PASO 75 COMPLETO ===')
    print(f'Area mediana OA (n=292): {median_ha:,.6f} ha')
    print(f'Reparaciones geométricas OA: {len(audit)} | auditoría: {audit_csv}')
    print(f'Diametro circular equivalente teorico: {diameter_reference:,.3f} m')
    print(f'55 buffers; desvío max area: {report["desviacion_maxima_area_m2"]:.6f} m2')
    print('Archivos:',OUT,REPORT/'75_control_buffers_mediana_oa.json')
if __name__=='__main__': main()
