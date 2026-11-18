#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 67: matriz COCHILCO por proyecto, mineral y componentes IST puntual.

No inventa superficies de proyectos. Requiere paso 66 completo.
Cruza por nombre normalizado EXACTO y ÚNICO; discrepancias se reportan y
bloquean la publicación de la matriz final, nunca se fuerzan uniones dudosas.

Uso: python -u src/67_matriz_proyectos_minerales_ist.py
"""
from __future__ import annotations
from pathlib import Path
import re
import unicodedata
import json
import pandas as pd
import geopandas as gpd

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/enmc'
BASE=ROOT/'data/processed/enmc'
COMP=['AP','SB','GL','HU','AI','CI','AD','PO','TU']


def norm(v):
    s=unicodedata.normalize('NFKD',str(v or '').casefold())
    s=''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+','',s)


def read_table(f):
    if not f.is_file(): raise FileNotFoundError(f)
    return pd.read_csv(f,encoding='utf-8-sig',dtype={'id_fuente':str})


def main():
    print('=== PASO 67: MATRIZ POR PROYECTO/MINERAL ===',flush=True)
    ist=read_table(REPORT/'66_ist_puntual_homologado.csv')
    ctl=REPORT/'66_control_ist_puntual.json'
    if not ctl.exists() or json.loads(ctl.read_text(encoding='utf-8'))['estado']!='COMPLETO':
        raise RuntimeError('Paso 66 no confirmado completo')
    ist=ist.loc[ist.fuente.eq('COCHILCO_ENMC')].copy()
    if len(ist)!=55 or ist[['fuente','id_fuente']].duplicated().any():
        raise RuntimeError('IST COCHILCO debe contener 55 proyectos únicos')
    # La matriz 28 tiene 55 registros verificados en fuentes y atributos,
    # aunque las geometrías propias de los proyectos continúen pendientes.
    matrixfile=REPORT/'28_matriz_geometrias_enmc_completada.csv'
    fallback=REPORT/'25_cochilco_enmc_revision.csv'
    source=matrixfile if matrixfile.exists() else fallback
    attr=read_table(source)
    if len(attr)!=55 or 'proyecto' not in attr.columns:
        raise RuntimeError(f'Matriz de proyectos inesperada: {source}')
    attr['_key']=attr.proyecto.map(norm)
    ist['_key']=ist.nombre.map(norm)
    if attr._key.duplicated().any() or ist._key.duplicated().any():
        raise RuntimeError('Nombres normalizados duplicados: requiere identificador estable')
    # No confiar en el orden de filas ni en el consecutivo implícito de COCHILCO.
    compare=ist[['_key','nombre','id_fuente']].merge(attr[['_key','proyecto']],on='_key',how='outer',indicator=True)
    if not compare._merge.eq('both').all():
        problem=compare.loc[compare._merge.ne('both')]
        problem.to_csv(REPORT/'67_nombres_sin_correspondencia.csv',index=False,encoding='utf-8-sig')
        raise RuntimeError('Nombres no coinciden; revisar reports/enmc/67_nombres_sin_correspondencia.csv (sin aproximación automática)')
    keep=['_key','fila_xls','proyecto','minerales_enmc','region','tipo_proyecto','tipo_proy','etapa','condicion',
          'geometria_nueva_verificada','estado_verificacion','proy_seia','id_expediente_seia']
    keep=[c for c in keep if c in attr.columns]
    data=ist.merge(attr[keep],on='_key',how='inner',validate='one_to_one').drop(columns=['_key'])
    if len(data)!=55: raise RuntimeError('La unión no produjo 55 registros')
    data['superficie_proyecto_ha']=pd.NA
    data['estado_superficie']='NO_DISPONIBLE_POLIGONO_VERIFICADO'
    data['tipo_IST']='PUNTUAL_HOMOLOGADO'
    cols=['id_fuente','proyecto','nombre','minerales_enmc','region','etapa','condicion','IST_100',
          'superficie_proyecto_ha','estado_superficie','tipo_IST']
    cols += [f'S_{c}' for c in COMP]+[f'A_{c}' for c in COMP]+[f'd_{c}_km' for c in COMP]
    cols += [c for c in ('fila_xls','proy_seia','id_expediente_seia','estado_verificacion') if c in data]
    cols=[c for c in cols if c in data.columns]
    data[cols].to_csv(REPORT/'67_proyectos_minerales_ist_puntual.csv',index=False,encoding='utf-8-sig')
    # Si varios minerales están codificados en la misma fila, desagregar de manera
    # explícita conservando el id de proyecto, sin considerar los conteos aditivos.
    expanded=[]
    for _,r in data.iterrows():
        raw=str(r.get('minerales_enmc',''))
        materials=[p.strip() for p in re.split(r'[,;/|+]',raw) if p.strip()]
        if not materials: materials=['SIN_CLASIFICAR']
        for mineral in set(materials):
            record={'mineral':mineral,'id_fuente':r['id_fuente'],'proyecto':r['proyecto'],'IST_100':r['IST_100']}
            for c in COMP: record[f'A_{c}']=r[f'A_{c}']
            expanded.append(record)
    bymin=pd.DataFrame(expanded)
    bymin.to_csv(REPORT/'67_proyectos_minerales_formato_largo.csv',index=False,encoding='utf-8-sig')
    agg=bymin.groupby('mineral').agg(n_proyectos=('id_fuente','nunique'),
                                     ist_medio=('IST_100','mean'),ist_mediana=('IST_100','median'))
    for c in COMP: agg[f'aporte_medio_{c}']=bymin.groupby('mineral')[f'A_{c}'].mean()
    agg=agg.reset_index()
    agg.to_csv(REPORT/'67_resumen_ist_por_mineral.csv',index=False,encoding='utf-8-sig')
    if 'region' in data:
        reg=data.groupby('region',dropna=False).agg(n_proyectos=('id_fuente','nunique'),ist_medio=('IST_100','mean')).reset_index()
        reg.to_csv(REPORT/'67_resumen_ist_cochilco_por_region.csv',index=False,encoding='utf-8-sig')
    # Complemento OA: sin afirmar actividad vigente, región tomada de atributo original.
    oa=ist_all=read_table(REPORT/'66_ist_puntual_homologado.csv')
    oa=oa.loc[oa.fuente.eq('OA_ENMC')].copy()
    sourceoa=gpd.read_file(BASE/'oa_enmc_candidatas.gpkg',engine='pyogrio')
    sourceoa=sourceoa.loc[sourceoa.estado_oa_provisional.eq('CANDIDATA_OPERACION_POR_TIPO')].copy()
    if 'REGION' not in sourceoa: raise RuntimeError('OA no tiene REGION')
    sourceoa['id_fuente']=sourceoa.OBJECTID.astype(str)
    oa=oa.merge(sourceoa[['id_fuente','REGION']],on='id_fuente',how='left',validate='one_to_one')
    if len(oa)!=292 or oa.REGION.isna().any(): raise RuntimeError('Error en asignación región OA')
    oreg=oa.groupby('REGION').agg(n_oa=('id_fuente','size'),ist_medio=('IST_100','mean')).reset_index()
    oreg.to_csv(REPORT/'67_resumen_ist_oa_por_region.csv',index=False,encoding='utf-8-sig')
    print('Proyectos:',len(data),'| Minerales distintos:',len(agg),flush=True)
    print(agg[['mineral','n_proyectos','ist_medio']].to_string(index=False),flush=True)
    print('IMPORTANTE: suma n_proyectos por mineral puede exceder 55 si hay proyectos multiminéricos.',flush=True)
    print('PASO 67 FINALIZADO',flush=True)

if __name__=='__main__': main()
