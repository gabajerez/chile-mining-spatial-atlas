#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 76: IST geométrico OA(poligonos) vs COCHILCO(buffers medianos), y minerales OA.
Recalculo de nueve componentes por distancias a geometria completa, no desde punto.
Salidas separadas del IST puntual (paso 66). No certifica operacion vigente.
"""
from pathlib import Path
import argparse, json, math, re, unicodedata
from datetime import datetime,timezone
import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from pyproj import CRS,Transformer
from shapely.ops import transform

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/processed/enmc'; SENS=BASE/'sensibilidad'; REPORT=ROOT/'reports/enmc'; DOC=ROOT/'docs/informes'
CRS_AREA='EPSG:6933'
COMP={
 'AP':(('areas_protegidas',),(1,5,10,25),.165),
 'SB':(('sitios_prioritarios','reservas_biosfera'),(1,5,10,25),.099),
 'GL':(('glaciares',),(.5,2,10,25),.133),
 'HU':(('humedales_mma_nacional',),(1,5,10,25),.120),
 'AI':(('planes_atmosfericos',),(.5,5,25,50),.170),
 'CI':(('comunidades_indigenas',),(2,10,25,50),.131),
 'AD':(('areas_desarrollo_indigena',),(2,10,25,50),.065),
 'PO':(('areas_pobladas',),(2,5,15,30),.070),
 'TU':(('atractivos_turisticos','zonas_interes_turistico'),(.5,2,5,10),.047)
}
assert abs(sum(z[2] for z in COMP.values())-1.)<1e-10

def read(path):
    if not path.exists(): raise FileNotFoundError(path)
    g=gpd.read_file(path,engine='pyogrio')
    if g.crs is None: raise ValueError(f'Sin CRS: {path}')
    if g.geometry.isna().any() or g.geometry.is_empty.any(): raise ValueError(f'Geometria nula: {path}')
    if not g.geometry.is_valid.all(): g['geometry']=g.geometry.map(shapely.make_valid)
    return g.to_crs(CRS_AREA)

def canonical(s):
    s=unicodedata.normalize('NFKD',str(s).casefold())
    return re.sub(r'\s+',' ',''.join(c for c in s if not unicodedata.combining(c))).strip()

def prepare():
    oa=read(BASE/'oa_enmc_candidatas.gpkg')
    oa=oa.loc[oa.estado_oa_provisional.eq('CANDIDATA_OPERACION_POR_TIPO')].copy()
    if len(oa)!=292 or not oa.geom_type.isin(['Polygon','MultiPolygon']).all():
        raise ValueError('Universo de huellas OA no es 292 polígonos')
    if not {'OBJECTID','MINERAL','minerales_enmc','REGION','NOMBRE'}.issubset(oa.columns):
        raise ValueError('OA carece de mineral u otros atributos auditables')
    oa['fuente']='OA_ENMC';oa['id_fuente']=oa.OBJECTID.astype(str)
    oa['nombre']=oa.NOMBRE.astype(str)
    oa['tipo_geometria_calculo']='POLIGONO_OA_COMPLETO'
    oa['mineral_oa_original']=oa.MINERAL.astype(str)
    oa['minerales_enmc']=oa.minerales_enmc.astype(str)
    oa['region_origen']=oa.REGION.astype(str)
    buffers=read(BASE/'75_cochilco_buffers_mediana_oa.gpkg')
    if len(buffers)!=55 or buffers.id_fuente.astype(str).duplicated().any():
        raise ValueError('Los 55 buffers no son únicos')
    coch=read(BASE/'cochilco_enmc_proyectos.gpkg')
    ident=next((x for x in ('id_proyecto','ID_PROY','ID','OBJECTID') if x in coch),None)
    if ident is None:
        coch['id_calculo']=range(1,len(coch)+1);ident='id_calculo'
    nam=next((x for x in ('NOMBRE','nombre','PROYECTO','proyecto') if x in coch),None)
    if nam is None: raise KeyError('Nombre COCHILCO')
    coch['id_fuente']=coch[ident].astype(str)
    if coch.id_fuente.duplicated().any(): raise ValueError('ID COCHILCO repetidos')
    projects=buffers.merge(coch[['id_fuente',nam]],on='id_fuente',validate='one_to_one',how='inner')
    if len(projects)!=55: raise ValueError('No se lograron asociar todos los buffers')
    projects['fuente']='COCHILCO_ENMC';projects['nombre']=projects[nam].astype(str)
    projects['tipo_geometria_calculo']='BUFFER_CIRCULAR_MEDIANA_OA'
    for k in ('mineral_oa_original','minerales_enmc','region_origen'):
        projects[k]=pd.NA
    cols=['fuente','id_fuente','nombre','tipo_geometria_calculo','mineral_oa_original','minerales_enmc','region_origen','geometry']
    combined=gpd.GeoDataFrame(pd.concat([oa[cols],projects[cols]],ignore_index=True),geometry='geometry',crs=CRS_AREA)
    if combined[['fuente','id_fuente']].duplicated().any():raise ValueError('IDs repetidos')
    if combined.fuente.value_counts().to_dict()!={'OA_ENMC':292,'COCHILCO_ENMC':55}:
        raise ValueError('Universo no corresponde a 292+55')
    return combined

def score(km,limits):
    for val,limit in zip((1,.75,.5,.25),limits):
        if km<=limit+1e-9:return val
    return 0.

def main():
    pa=argparse.ArgumentParser()
    pa.add_argument('--limit',type=int,default=None,help='Prueba: primeras N unidades por fuente')
    pa.add_argument('--resume',action='store_true')
    pa.add_argument('--save-every',type=int,default=5)
    args=pa.parse_args()
    if args.limit is not None and args.limit<1:raise ValueError('limit debe ser positivo')
    REPORT.mkdir(parents=True,exist_ok=True);DOC.mkdir(parents=True,exist_ok=True)
    universe=prepare()
    units=universe.groupby('fuente',sort=False,group_keys=False).head(args.limit).copy() if args.limit else universe
    suffix='_PRUEBA' if args.limit else ''
    out=REPORT/f'76_ist_poligonos_buffers{suffix}.csv'
    existing=pd.DataFrame()
    if args.resume and out.exists():
        existing=pd.read_csv(out,encoding='utf-8-sig',dtype={'id_fuente':str})
        if existing[['fuente','id_fuente']].duplicated().any():raise ValueError('Resultado reanudado duplicado')
        keys=set(zip(units.fuente,units.id_fuente))
        if not set(zip(existing.fuente,existing.id_fuente)).issubset(keys):raise ValueError('Resultados ajenos a universo')
    elif out.exists():
        raise FileExistsError(f'{out} ya existe. Usar --resume o renombrar el archivo.')
    done=set(zip(existing.fuente,existing.id_fuente)) if not existing.empty else set()
    frames={}
    for names,_,_ in COMP.values():
        for name in names:
            if name not in frames:
                path=SENS/('56_humedales_mma_nacional.gpkg' if name=='humedales_mma_nacional' else f'39_{name}.gpkg')
                frames[name]=read(path)[['geometry']].reset_index(drop=True)
                print(f'{name}: {len(frames[name])}',flush=True)
    to_ll=Transformer.from_crs(CRS_AREA,'EPSG:4326',always_xy=True).transform
    fresh=[]
    def save():
        allrows=pd.concat([existing,pd.DataFrame(fresh)],ignore_index=True)
        tmp=out.with_suffix('.partial.csv')
        allrows.to_csv(tmp,index=False,encoding='utf-8-sig');tmp.replace(out)
    for idx,rec in enumerate(units.itertuples(index=False),1):
        if (rec.fuente,rec.id_fuente) in done:continue
        geom=rec.geometry
        center=geom.representative_point()
        pointll=transform(to_ll,center)
        local=CRS.from_proj4(f'+proj=aeqd +lat_0={pointll.y:.10f} +lon_0={pointll.x:.10f} +datum=WGS84 +units=m +no_defs')
        to_local=Transformer.from_crs(CRS_AREA,local,always_xy=True).transform
        unitloc=transform(to_local,geom)
        row={'fuente':rec.fuente,'id_fuente':rec.id_fuente,'nombre':rec.nombre,
             'tipo_geometria_calculo':rec.tipo_geometria_calculo,
             'mineral_oa_original':rec.mineral_oa_original,'minerales_enmc':rec.minerales_enmc,
             'region_origen':rec.region_origen,'area_geometria_ha':geom.area/1e4}
        total=0.
        query=geom.buffer(200000).envelope
        for code,(names,bands,w) in COMP.items():
            best=float('inf');candidates=0
            for name in names:
                layer=frames[name]
                ids=layer.sindex.query(query,predicate='intersects')
                candidates+=len(ids)
                for idx2 in ids:
                    d=unitloc.distance(transform(to_local,layer.geometry.iloc[int(idx2)]))
                    if d<best:best=d
                    if best<=1e-7:break
                if best<=1e-7:break
            km=best/1000
            s=score(km,bands)
            row[f'd_{code}_km']=round(km,6) if math.isfinite(km) else np.nan
            row[f'S_{code}']=s;row[f'A_{code}']=round(w*100*s,6)
            row[f'sin_candidatos_{code}']=not math.isfinite(km)
            total+=100*w*s
        row['IST_100']=round(total,6)
        fresh.append(row)
        if len(fresh)%args.save_every==0:
            save();print(f'{idx}/{len(units)} | {rec.fuente} | IST={total:.3f}',flush=True)
    if fresh:save()
    final=pd.read_csv(out,encoding='utf-8-sig',dtype={'id_fuente':str})
    final=final.sort_values(['fuente','id_fuente']).reset_index(drop=True)
    if len(final)!=len(units):raise RuntimeError('Proceso parcial: reanudar con --resume')
    if not np.allclose(final[[f'A_{c}' for c in COMP]].sum(axis=1),final.IST_100,atol=2e-5):
        raise ValueError('Balance IST no coincide con aportes')
    if not final.IST_100.between(0,100).all():raise ValueError('IST fuera de rango')
    report=final.groupby('fuente').IST_100.agg(['count','mean','median','min','max'])
    report.to_csv(REPORT/f'76_resumen_fuentes{suffix}.csv',encoding='utf-8-sig')
    if not args.limit:
        oa=final.loc[final.fuente.eq('OA_ENMC')].copy()
        # Usar clasificacion ya auditada de OA, sin inferir mineral desde el nombre.
        # Cada unidad puede tener mas de un mineral y se declarara multietiqueta.
        oa['mineral_etiqueta']=oa.minerales_enmc.fillna('').astype(str).map(canonical)
        if oa.mineral_etiqueta.isin(['','nan','none']).any():
            missing=oa.loc[oa.mineral_etiqueta.isin(['','nan','none']),['id_fuente','nombre']]
            missing.to_csv(REPORT/'76_oa_sin_mineral_auditoria.csv',index=False,encoding='utf-8-sig')
            raise ValueError('OA tiene registros sin mineral; revisar CSV de auditoria antes de resumir')
        # Permitir formatos multietiqueta explícitos, sin cambiar el origen.
        def split_labels(s):
            parts=[x.strip() for x in re.split(r'[,;/|+]',s) if x.strip()]
            return sorted(set(parts))
        expanded=oa.assign(mineral=oa.mineral_etiqueta.map(split_labels)).explode('mineral')
        if expanded.mineral.isna().any():raise ValueError('Etiqueta de mineral vacia')
        expanded.to_csv(REPORT/'76_oa_unidades_por_mineral.csv',index=False,encoding='utf-8-sig')
        aggs={'n_huellas_unicas':('id_fuente','nunique'),'ist_medio':('IST_100','mean'),'ist_mediana':('IST_100','median'),
               'area_ha_individual_suma':('area_geometria_ha','sum')}
        for k in COMP:aggs[f'aporte_medio_{k}']= (f'A_{k}','mean')
        mineral=expanded.groupby('mineral').agg(**aggs).reset_index().sort_values('n_huellas_unicas',ascending=False)
        mineral.to_csv(REPORT/'76_oa_resumen_por_mineral.csv',index=False,encoding='utf-8-sig')
        region=expanded.groupby(['region_origen','mineral']).agg(**aggs).reset_index()
        region.to_csv(REPORT/'76_oa_mineral_por_region.csv',index=False,encoding='utf-8-sig')
        if len(oa)!=292: raise ValueError('Universo OA incompleto')
        meta={'estado':'COMPLETO','fecha_utc':datetime.now(timezone.utc).isoformat(),
              'fuentes':{'OA':292,'COCHILCO':55},'medida':'distancia minima desde geometria completa',
              'oa':'huellas OA poligonales provisionales; mineral de campo minerales_enmc con auditoria MINERAL',
              'proyectos':'buffer circular calibrado a mediana de area individual OA',
              'n_etiquetas_oa':int(len(expanded)), 'n_minerales_distintos_oa':int(mineral.shape[0]),
              'no_sumar_areas_entre_minerales':'huellas multiminéricos pueden duplicarse entre grupos',
              'fuente_HU':'Inventario MMA 56',
              'limitacion':'No representa ocupacion futura verificada ni actividad OA confirmada'}
        (REPORT/'76_control_ist_geometrico_minerales_oa.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False),encoding='utf-8')
        md=['# Resultados OA por mineral e IST geométrico con buffers equivalentes','',
            '## Metodología','',
            'Se conserva la geometría poligonal OA y se sustituyen los puntos de proyectos por círculos de igual área a la mediana de las 292 huellas OA seleccionadas. El diámetro se estima con la fórmula de equivalencia circular y cada círculo se ajusta métricamente para reproducir la superficie objetivo en EPSG:6933. No se interpretan como huellas de proyectos reales.','',
            'El IST se vuelve a calcular desde la geometría completa con las nueve bandas y ponderaciones originales, usando la fuente de humedales MMA actualizada. Los resultados del IST puntual del paso 66 no se sobrescriben.','',
            '## Resultado por fuente','',report.to_markdown(),'','## OA por mineral','',mineral.to_markdown(index=False,floatfmt='.3f'),'',
            '## Archivos','',
            '- [Matriz IST 347 unidades](../../reports/enmc/76_ist_poligonos_buffers.csv)',
            '- [OA por mineral, detalle](../../reports/enmc/76_oa_unidades_por_mineral.csv)',
            '- [Resumen OA por mineral](../../reports/enmc/76_oa_resumen_por_mineral.csv)',
            '- [OA por region y mineral](../../reports/enmc/76_oa_mineral_por_region.csv)',
            '- [Controles](../../reports/enmc/76_control_ist_geometrico_minerales_oa.json)',
            '- [Calibración de buffers](../../reports/enmc/75_control_buffers_mediana_oa.json)','',
            '## Límites interpretativos','',
            'Los minerales se asocian a huellas OA con una selección de operación provisional; no prueban faenas activas. Las áreas individuales de huellas pueden superponerse, por lo que su suma no equivale a huella disuelta sin doble conteo. Los grupos multiminéricos pueden contabilizar una huella en más de una categoría. Las concesiones no tienen mineral identificado.','']
        (DOC/'76_resultados_oa_minerales_y_buffers.md').write_text('\n'.join(md),encoding='utf-8')
        integral=DOC/'INFORME_INTEGRAL_ENMC.md'
        if integral.is_file():
            start='<!-- ENMC_GEOMETRIAS_EQUIVALENTES_INICIO -->'
            end='<!-- ENMC_GEOMETRIAS_EQUIVALENTES_FIN -->'
            block=(f'{start}\n\n## Actualización: buffers equivalentes y minerales OA\n\n'
                   'La comparación adicional usa la geometría completa de las 292 huellas OA y '
                   'buffers de área equivalente a la mediana de esas huellas para los 55 puntos de proyectos. '
                   'Son círculos analíticos, no polígonos de intervención. '
                   'La comparación puntual del paso 66 se conserva por separado.\n\n'
                   f'- Superficie mediana OA y diámetro: [control paso 75](../../reports/enmc/75_control_buffers_mediana_oa.json).\n'
                   f'- [Informe por mineral OA y nuevo IST](76_resultados_oa_minerales_y_buffers.md).\n'
                   f'- [Resultados individuales](../../reports/enmc/76_ist_poligonos_buffers.csv).\n'
                   f'- [Resultados por mineral OA](../../reports/enmc/76_oa_resumen_por_mineral.csv).\n\n'
                   f'{end}\n')
            old=integral.read_text(encoding='utf-8')
            if start in old and end in old:
                old=old[:old.index(start)]+old[old.index(end)+len(end):].lstrip('\n')
            integral.write_text(old.rstrip('\n')+'\n\n'+block,encoding='utf-8')
            print('Informe integral existente actualizado:',integral,flush=True)
    print('=== PASO 76 COMPLETO ===');print(report.to_string())
    if not args.limit:print('OA por mineral: reports/enmc/76_oa_resumen_por_mineral.csv')
if __name__=='__main__':main()
