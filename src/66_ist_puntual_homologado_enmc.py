#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 66: IST ENMC puntual homologado, sin sustituir IST poligonal.

OA: representative_point() interior de cada geometría (nunca borde entero).
COCHILCO: punto proporcionado en la capa (sin buffer).
Distancias: AEQD local por unidad, selección espacial EPSG:6933.
Humedales: inventario nacional MMA paso 56b; otras diez fuentes paso 39.

Ejemplos:
  python -u src/66_ist_puntual_homologado_enmc.py --limit 3
  python -u src/66_ist_puntual_homologado_enmc.py
  python -u src/66_ist_puntual_homologado_enmc.py --resume
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
from datetime import datetime, timezone
import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from pyproj import CRS, Transformer
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/processed/enmc'
SENS = BASE / 'sensibilidad'
REPORT = ROOT / 'reports/enmc'
AREA_CRS = 'EPSG:6933'
# Componentes idénticos al paso 43; HU exclusivamente fuente MMA actualizada.
COMPONENTS = {
    'AP': (('areas_protegidas',), (1,5,10,25), .165),
    'SB': (('sitios_prioritarios','reservas_biosfera'), (1,5,10,25), .099),
    'GL': (('glaciares',), (.5,2,10,25), .133),
    'HU': (('humedales_mma_nacional',), (1,5,10,25), .120),
    'AI': (('planes_atmosfericos',), (.5,5,25,50), .170),
    'CI': (('comunidades_indigenas',), (2,10,25,50), .131),
    'AD': (('areas_desarrollo_indigena',), (2,10,25,50), .065),
    'PO': (('areas_pobladas',), (2,5,15,30), .070),
    'TU': (('atractivos_turisticos','zonas_interes_turistico'), (.5,2,5,10), .047),
}
EXPECTED = {'OA_ENMC':292, 'COCHILCO_ENMC':55}
assert abs(sum(v[2] for v in COMPONENTS.values())-1) < 1e-12


def read_gdf(path):
    if not path.is_file():
        raise FileNotFoundError(f'No existe insumo: {path}')
    g = gpd.read_file(path, engine='pyogrio')
    if g.crs is None:
        raise ValueError(f'CRS indefinido: {path}')
    if g.geometry.isna().any() or g.geometry.is_empty.any():
        raise ValueError(f'Geometrías vacías/nulas: {path}')
    if not g.geometry.is_valid.all():
        g['geometry'] = g.geometry.map(lambda x: shapely.make_valid(x))
    return g.to_crs(AREA_CRS)


def prepare_units():
    oa = read_gdf(BASE/'oa_enmc_candidatas.gpkg')
    oa = oa.loc[oa.estado_oa_provisional.eq('CANDIDATA_OPERACION_POR_TIPO')].copy()
    if 'OBJECTID' not in oa or 'NOMBRE' not in oa:
        raise RuntimeError('Falta OBJECTID o NOMBRE en OA')
    oa['fuente'] = 'OA_ENMC'
    oa['id_fuente'] = oa['OBJECTID'].astype(str)
    oa['nombre'] = oa['NOMBRE'].astype(str)
    oa['criterio_punto'] = 'PUNTO_INTERIOR_OA'
    oa['geometry'] = oa.geometry.representative_point()

    coch = read_gdf(BASE/'cochilco_enmc_proyectos.gpkg')
    ident = next((x for x in ('id_proyecto','ID_PROY','ID','OBJECTID') if x in coch), None)
    if ident is None:
        coch['id_calculo'] = range(1,len(coch)+1)
        ident = 'id_calculo'
    colname = next((x for x in ('NOMBRE','nombre','PROYECTO','proyecto') if x in coch),None)
    if colname is None:
        raise RuntimeError('COCHILCO: no se halló campo de nombre')
    if not coch.geom_type.isin(['Point','MultiPoint']).all():
        raise RuntimeError('COCHILCO no está íntegramente representada por puntos')
    coch['fuente'] = 'COCHILCO_ENMC'
    coch['id_fuente'] = coch[ident].astype(str)
    coch['nombre'] = coch[colname].astype(str)
    coch['criterio_punto'] = 'PUNTO_FUENTE_COCHILCO'
    if (coch.geom_type=='MultiPoint').any():
        raise RuntimeError('Hay MultiPoint en COCHILCO: resolver localización antes del cálculo')
    both = pd.concat([oa[['fuente','id_fuente','nombre','criterio_punto','geometry']],
                      coch[['fuente','id_fuente','nombre','criterio_punto','geometry']]],ignore_index=True)
    both = gpd.GeoDataFrame(both, geometry='geometry',crs=AREA_CRS)
    if both[['fuente','id_fuente']].duplicated().any():
        raise RuntimeError('Identificadores duplicados')
    got = both.fuente.value_counts().to_dict()
    if got != EXPECTED:
        raise RuntimeError(f'Universo inesperado {got}, se esperaba {EXPECTED}')
    return both


def local_transform(point, to_lonlat):
    point_ll = transform(to_lonlat,point)
    crs = CRS.from_proj4(f'+proj=aeqd +lat_0={point_ll.y:.10f} +lon_0={point_ll.x:.10f} +datum=WGS84 +units=m +no_defs')
    return Transformer.from_crs(AREA_CRS,crs,always_xy=True).transform


def score(km, limits):
    for s, t in zip((1.,.75,.5,.25),limits):
        if km <= t + 1e-9:
            return s
    return 0.


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit',type=int,default=None,help='Prueba: primeras N unidades por fuente, sin sobrescribir resultados finales')
    ap.add_argument('--resume',action='store_true',help='Continuar resultados finales existentes')
    ap.add_argument('--chunk-save',type=int,default=10)
    args = ap.parse_args()
    if args.limit is not None and args.limit < 1:
        ap.error('--limit debe ser positivo')
    if args.resume and args.limit:
        ap.error('--resume y --limit no se combinan')
    if args.chunk_save < 1:
        ap.error('--chunk-save debe ser positivo')
    REPORT.mkdir(parents=True,exist_ok=True)
    suffix = '_PRUEBA' if args.limit else ''
    out = REPORT/f'66_ist_puntual_homologado{suffix}.csv'
    control = REPORT/f'66_control_ist_puntual{suffix}.json'
    print('=== PASO 66: IST PUNTUAL HOMOLOGADO ===',flush=True)
    units = prepare_units()
    if args.limit:
        units = units.groupby('fuente',sort=False,group_keys=False).head(args.limit).copy()
    existing = pd.DataFrame()
    if args.resume and out.exists():
        existing = pd.read_csv(out, encoding='utf-8-sig', dtype={'id_fuente':str})
        if existing[['fuente','id_fuente']].duplicated().any():
            raise RuntimeError('CSV previo contiene ids duplicados')
        eligible = set(zip(units.fuente,units.id_fuente))
        if not set(zip(existing.fuente,existing.id_fuente)).issubset(eligible):
            raise RuntimeError('CSV de continuación contiene unidades ajenas')
        print('Continuando',len(existing),'unidades',flush=True)
    elif out.exists():
        raise RuntimeError(f'Archivo ya existe: {out}. Usar --resume para conservarlo o renombrarlo para reiniciar.')
    completed = set(zip(existing.fuente,existing.id_fuente)) if not existing.empty else set()
    # Cargar una vez, conservando geometrías completas y sin forzar uniones globales.
    layers = {}
    for names,_,_ in COMPONENTS.values():
        for n in names:
            if n in layers: continue
            f = SENS/('56_humedales_mma_nacional.gpkg' if n=='humedales_mma_nacional' else f'39_{n}.gpkg')
            layers[n] = read_gdf(f)[['geometry']].reset_index(drop=True)
            print(f'  {n}: {len(layers[n])} geometrías',flush=True)
    to_ll = Transformer.from_crs(AREA_CRS,'EPSG:4326',always_xy=True).transform
    new=[]
    def save():
        combined = pd.concat([existing,pd.DataFrame(new)],ignore_index=True)
        if combined[['fuente','id_fuente']].duplicated().any(): raise RuntimeError('Resultados duplicados')
        tmp=out.with_suffix('.partial.csv')
        combined.to_csv(tmp,index=False,encoding='utf-8-sig')
        tmp.replace(out)
    for index,rec in enumerate(units.itertuples(index=False),1):
        key = (rec.fuente,str(rec.id_fuente))
        if key in completed: continue
        p = rec.geometry
        if p.geom_type != 'Point': raise RuntimeError(f'No es punto: {key}')
        tr = local_transform(p,to_ll)
        local_p = transform(tr,p)
        result={'fuente':rec.fuente,'id_fuente':rec.id_fuente,'nombre':rec.nombre,
                'modo_geometria':'PUNTO_HOMOLOGADO','criterio_punto':rec.criterio_punto,
                'estado_operativo':'NO_CONFIRMADO' if rec.fuente=='OA_ENMC' else 'NO_APLICA_PROYECTO'}
        total=0.
        # Conservador para vecinos de <=50 km; la distancia real se calcula en AEQD.
        query = p.buffer(200_000).envelope
        for code,(names,thresholds,weight) in COMPONENTS.items():
            minimum=float('inf'); count=0
            for name in names:
                frame=layers[name]
                ids=frame.sindex.query(query,predicate='intersects')
                count += len(ids)
                for geom in frame.geometry.iloc[ids]:
                    d=local_p.distance(transform(tr,geom))
                    if d < minimum: minimum=d
                    if minimum <= 1e-7: break
                if minimum <= 1e-7: break
            km=minimum/1000.
            sc=score(km,thresholds)
            result[f'd_{code}_km']=round(km,6) if math.isfinite(km) else None
            result[f'S_{code}']=sc
            result[f'A_{code}']=round(100*weight*sc,6)
            result[f'candidatos_{code}']=count
            result[f'sin_candidatos_{code}']=not math.isfinite(km)
            total+=weight*sc
        result['IST_01']=round(total,8)
        result['IST_100']=round(100*total,6)
        new.append(result)
        if len(new)%args.chunk_save==0 or index==len(units):
            save()
            print(f'  {index}/{len(units)} | {rec.fuente} | IST={result["IST_100"]:.2f} | guardado',flush=True)
    if not new and existing.empty: raise RuntimeError('Sin resultados')
    if new and len(new)%args.chunk_save: save()
    final=pd.read_csv(out,encoding='utf-8-sig',dtype={'id_fuente':str})
    finished=len(final)==len(units)
    if finished:
        if not final.IST_100.between(0,100).all(): raise RuntimeError('Valores IST fuera de rango')
        if not np.allclose(final[[f'A_{k}' for k in COMPONENTS]].sum(axis=1),final.IST_100,atol=2e-5):
            raise RuntimeError('La suma de componentes no reproduce IST')
        totals=final.groupby('fuente').IST_100.agg(['size','mean','median','min','max'])
        totals.to_csv(REPORT/f'66_resumen_ist_puntual{suffix}.csv',encoding='utf-8-sig')
        print(totals.to_string(),flush=True)
    meta={'estado':'COMPLETO' if finished else 'PARCIAL','fecha_utc':datetime.now(timezone.utc).isoformat(),
          'n_unidades':len(final),'n_esperadas':len(units),
          'criterio_OA':'representative_point interior, no centroide geométrico',
          'criterio_COCHILCO':'punto de localización registrado',
          'medicion':'distancia mínima desde punto, AEQD local',
          'fuente_humedales':'56_humedales_mma_nacional.gpkg',
          'resto_fuentes':'39_*.gpkg','nota':'No equivale a superficie de proyecto ni impacto ambiental'}
    control.write_text(json.dumps(meta,indent=2,ensure_ascii=False),encoding='utf-8')
    print('Tabla:',out,'| estado:',meta['estado'],flush=True)
    if not finished: raise RuntimeError('Salida parcial; volver a ejecutar con --resume')
    print('PASO 66 FINALIZADO',flush=True)

if __name__=='__main__': main()
