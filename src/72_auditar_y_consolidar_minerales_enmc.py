#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 72: audita procedencia mineral de 55 proyectos y consolida IST por mineral/región.

No asigna un mineral a concesiones constituidas. No interpreta buffers como huellas
mineras. Se ejecuta desde la raiz del repositorio MAPAS_GM.

Insumos obligatorios:
 reports/enmc/67_proyectos_minerales_ist_puntual.csv
 reports/enmc/67_proyectos_minerales_formato_largo.csv
 reports/enmc/69_ist_puntual_unidades_con_region.csv
 data/processed/enmc/cochilco_enmc_proyectos.gpkg

Insumos de auditoria (buscar en rutas alternativas, opcionales):
 audit_enmc_cochilco_detalle.csv y/o cochilco_integracion_proyectos.csv.
 Si no existen: se documenta procedencia NO VERIFICADA, sin presumir que sí.

Salidas: reports/enmc/72_*.csv / json; outputs/figures/enmc/72_*.png;
 docs/informes/72_resultados_por_mineral_ENMC.md
"""
from __future__ import annotations
import json
import re
import unicodedata
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports' / 'enmc'
FIG = ROOT / 'outputs' / 'figures' / 'enmc'
DOC = ROOT / 'docs' / 'informes'
COMP = ('AP','SB','GL','HU','AI','CI','AD','PO','TU')
LABELS = {
    'AP':'Áreas protegidas','SB':'Prioritarios + biosfera','GL':'Glaciares',
    'HU':'Humedales MMA','AI':'Planes atmosféricos','CI':'Comunidades indígenas',
    'AD':'Desarrollo indígena','PO':'Áreas pobladas','TU':'Turismo'
}


def canonical(x):
    s = unicodedata.normalize('NFKD',str(x).strip().casefold())
    return re.sub(r'[^a-z0-9]+','', ''.join(c for c in s if not unicodedata.combining(c)))


def csv(path):
    if not path.exists(): raise FileNotFoundError(path)
    return pd.read_csv(path,encoding='utf-8-sig',dtype={'id_fuente':'string'})


def source_file(name):
    candidates = [ROOT/name, REPORT/name, ROOT/'outputs'/'tables'/name, ROOT/'data'/'raw'/name]
    return next((p for p in candidates if p.is_file()),None)


def assert_no_duplicate(df,keys,label):
    if df.duplicated(keys).any():
        bad=df.loc[df.duplicated(keys,keep=False),keys]
        raise ValueError(f'{label}: claves duplicadas: {bad.head(5).to_dict("records")}')


def write_csv(df,name):
    path=REPORT/name
    df.to_csv(path,index=False,encoding='utf-8-sig')
    return path


def audit_source(final):
    """Audit names against independent 57-row table, when available."""
    audit_name = 'audit_enmc_cochilco_detalle.csv'
    p = source_file(audit_name)
    info = {'archivo_auditoria_original': str(p.relative_to(ROOT)) if p and p.is_relative_to(ROOT) else (str(p) if p else None),
            'estado':'SIN_FUENTE_INDEPENDIENTE'}
    if p is None:
        secondary=source_file('cochilco_integracion_proyectos.csv')
        if secondary is None:
            print('ADVERTENCIA: no hay tabla independiente de 57 filas. Clasificacion por mineral PROVISIONAL.',flush=True)
            return info
        original=csv(secondary)
        if len(original)!=57 or not {'proyecto','mineral'}.issubset(original.columns):
            raise ValueError('Integracion historica original: se esperaban 57 registros con proyecto y mineral')
        # Etiquetas normalizadas explícitas y verificables contra la tabla de origen.
        # No se deriva el mineral del nombre de la institución fuente.
        mineral_map={'cobre':'cobre','hierro':'hierro','oro':'oro','litio':'litio',
                     'yodo y sal':'yodo','tierras ra':'tierras_raras',
                     'carbonato':None,'yeso':None}
        labels=original.mineral.astype(str).str.strip().str.casefold().map(mineral_map)
        unknown=original.loc[~original.mineral.astype(str).str.strip().str.casefold().isin(mineral_map)]
        if not unknown.empty: raise ValueError('Minerales no reconocidos en fuente de integración histórica')
        included=original.loc[labels.notna()].copy()
        excluded=original.loc[labels.isna()].copy()
        included['mineral_auditoria']=labels.loc[labels.notna()].to_numpy()
        included['_key']=included.proyecto.map(canonical)
        final['_key']=final.proyecto.map(canonical)
        assert_no_duplicate(included,['_key'],'Integracion histórica 57')
        assert_no_duplicate(final,['_key'],'Matriz final 55')
        compared=final[['id_fuente','proyecto','minerales_enmc','_key']].merge(
            included[['_key','proyecto','mineral_auditoria','mineral']],
            on='_key',how='outer',indicator=True,validate='one_to_one',suffixes=('_final','_origen'))
        write_csv(compared.drop(columns=['_key']),'72_auditoria_procedencia_minerales.csv')
        if len(included)!=55 or len(excluded)!=2 or not compared._merge.eq('both').all():
            raise ValueError('No existe correspondencia completa entre la cartera seleccionada y 57 registros originales')
        if not all(canonical(x)==canonical(y) for x,y in zip(compared.minerales_enmc,compared.mineral_auditoria)):
            raise ValueError('Etiquetas de mineral no coinciden con fuente historica')
        write_csv(excluded,'72_registros_excluidos_auditoria.csv')
        info.update({'archivo_auditoria_original':str(secondary),
                     'estado':'VALIDADA_CON_INTEGRACION_HISTORICA_55_DE_57',
                     'n_originales':57,'n_seleccionados':55,'n_excluidos':2,
                     'excluidos':excluded[['proyecto','mineral']].to_dict('records'),
                     'observacion':'Cruce con tabla de integracion historica; no sustituye revisión del origen primario XLS/SEIA'})
        return info
    src = csv(p)
    if not {'proyecto','enmc_si','minerales_enmc'}.issubset(src.columns):
        raise ValueError(f'Columnas de auditoria insuficientes: {p}')
    if len(src)!=57:
        raise ValueError(f'Auditoria original contiene {len(src)} filas, se esperaban 57')
    mask=src['enmc_si'].astype(str).str.strip().str.casefold().isin(('true','1','si','sí'))
    included=src.loc[mask].copy()
    excluded=src.loc[~mask].copy()
    if len(included)!=55 or len(excluded)!=2:
        raise ValueError(f'Universo original discrepante: seleccionados {len(included)}, descartados {len(excluded)}')
    src['_key']=src.proyecto.map(canonical)
    final['_key']=final.proyecto.map(canonical)
    assert_no_duplicate(src,['_key'],'Auditoria 57')
    assert_no_duplicate(final,['_key'],'Matriz final 55')
    compared=final[['id_fuente','proyecto','minerales_enmc','_key']].merge(
        included[['_key','proyecto','minerales_enmc','Mineral','fila_xls']].rename(
            columns={'proyecto':'nombre_original','minerales_enmc':'mineral_auditoria'}),
        how='outer',on='_key',validate='one_to_one',indicator=True)
    write_csv(compared.drop(columns=['_key']),'72_auditoria_procedencia_minerales.csv')
    if not compared['_merge'].eq('both').all():
        raise ValueError('Hay proyectos sin correspondencia exacta entre 55 y auditoria original')
    bad=compared.loc[[canonical(a)!=canonical(b) for a,b in zip(compared.minerales_enmc,compared.mineral_auditoria)]]
    if not bad.empty:
        raise ValueError('Clasificacion mineral difiere de la auditoria; ver 72_auditoria_procedencia_minerales.csv')
    write_csv(excluded.drop(columns=['_key']), '72_registros_excluidos_auditoria.csv')
    info.update({'estado':'VALIDADA_55_DE_57','n_originales':57,'n_seleccionados':55,
                 'n_excluidos':2,'excluidos':excluded[['proyecto','Mineral']].to_dict('records')})
    return info


def main():
    REPORT.mkdir(parents=True,exist_ok=True)
    FIG.mkdir(parents=True,exist_ok=True)
    DOC.mkdir(parents=True,exist_ok=True)
    print('=== PASO 72: AUDITORIA Y ANALISIS POR MINERAL ENMC ===',flush=True)
    project=csv(REPORT/'67_proyectos_minerales_ist_puntual.csv')
    long=csv(REPORT/'67_proyectos_minerales_formato_largo.csv')
    regions=csv(REPORT/'69_ist_puntual_unidades_con_region.csv')
    if len(project)!=55 or project.id_fuente.nunique()!=55:
        raise ValueError('Se requieren 55 proyectos unicos en paso 67')
    if not {'id_fuente','proyecto','minerales_enmc','IST_100'}.issubset(project.columns):
        raise ValueError('Faltan atributos basicos de proyecto/mineral/IST')
    if not {'id_fuente','mineral'}.issubset(long.columns):
        raise ValueError('Faltan id_fuente y mineral en formato largo')
    assert_no_duplicate(long,['id_fuente','mineral'],'Matriz mineral larga')
    if set(long.id_fuente)!=set(project.id_fuente):
        raise ValueError('IDs en matriz mineral larga no coinciden con proyectos')
    required=['IST_100']+[f'A_{c}' for c in COMP]+[f'S_{c}' for c in COMP]
    missing=[c for c in required if c not in project]
    if missing: raise ValueError(f'Columnas faltantes para IST: {missing}')
    for c in required:
        project[c]=pd.to_numeric(project[c],errors='raise')
    if not np.allclose(project[[f'A_{c}' for c in COMP]].sum(axis=1),project.IST_100,atol=1e-4):
        raise ValueError('IST no suma nueve aportes')
    region_co=regions.loc[regions.fuente.eq('COCHILCO_ENMC'),['id_fuente','region_espacial']].copy()
    if len(region_co)!=55 or region_co.region_espacial.isna().any():
        raise ValueError('Se requieren 55 COCHILCO regionalizados sin nulos del paso 69f')
    assert_no_duplicate(region_co,['id_fuente'],'Regionalizacion COCHILCO')
    base=project.merge(region_co,on='id_fuente',how='left',validate='one_to_one')
    if base.region_espacial.isna().any():
        raise ValueError('Proyecto sin region')
    # Comprobar la geometria utilizada por el IST (55 puntos), sin inferir geometria de proyecto.
    geo=ROOT/'data'/'processed'/'enmc'/'cochilco_enmc_proyectos.gpkg'
    if not geo.exists(): raise FileNotFoundError(geo)
    gdf=gpd.read_file(geo,engine='pyogrio')
    if len(gdf)!=55 or not gdf.geom_type.eq('Point').all():
        raise ValueError('Geometria COCHILCO no corresponde a 55 puntos')
    srcinfo=audit_source(project.copy())
    if not srcinfo['estado'].startswith('VALIDADA'):
        # Bloquear el producto final de interpretacion mineral cuando la auditoria no esta.
        print('La matriz se producira como PRELIMINAR; falta el CSV independiente de auditoria.',flush=True)
    expanded=long[['id_fuente','mineral']].merge(base,on='id_fuente',how='left',validate='many_to_one')
    if expanded.IST_100.isna().any(): raise ValueError('Expansión mineral incompleta')
    n_labels=int(len(expanded))
    n_unique=int(expanded.id_fuente.nunique())
    write_csv(expanded,'72_matriz_proyecto_mineral_region_componentes.csv')
    cols={'n_proyectos':('id_fuente','nunique'),'ist_medio':('IST_100','mean'),
          'ist_mediana':('IST_100','median'),'ist_minimo':('IST_100','min'),'ist_maximo':('IST_100','max')}
    for c in COMP:
        cols[f'aporte_medio_{c}']=(f'A_{c}','mean')
        cols[f'puntaje_medio_{c}']=(f'S_{c}','mean')
    bymin=expanded.groupby('mineral',dropna=False).agg(**cols).reset_index().sort_values('n_proyectos',ascending=False)
    byreg=expanded.groupby(['region_espacial','mineral'],dropna=False).agg(**cols).reset_index()
    write_csv(bymin,'72_resumen_mineral_ist_componentes.csv')
    write_csv(byreg,'72_resumen_region_mineral_ist.csv')
    print(bymin[['mineral','n_proyectos','ist_medio']].to_string(index=False),flush=True)
    # Heatmap de aportes (puntos del IST, no porcentajes de superficie)
    fig,ax=plt.subplots(figsize=(12, max(4, .72*len(bymin)+2)))
    vals=bymin[[f'aporte_medio_{c}' for c in COMP]].to_numpy(float)
    im=ax.imshow(vals,aspect='auto',cmap='YlOrRd',vmin=0)
    ax.set_xticks(range(len(COMP)),[LABELS[c] for c in COMP],rotation=42,ha='right')
    ax.set_yticks(range(len(bymin)),[f'{r.mineral} (n={r.n_proyectos})' for r in bymin.itertuples()])
    for (i,j),v in np.ndenumerate(vals):
        ax.text(j,i,f'{v:.1f}',ha='center',va='center',fontsize=8,
                color='white' if v>vals.max()*.57 else 'black')
    fig.colorbar(im,ax=ax,label='Aporte medio al IST (puntos)',fraction=.035,pad=.02)
    ax.set_title('Proyectos seleccionados: contribución media al IST puntual por mineral')
    fig.tight_layout()
    fig.savefig(FIG/'72_aportes_ist_por_mineral.png',dpi=180,bbox_inches='tight')
    plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,5))
    x=np.arange(len(bymin))
    ax.bar(x,bymin.ist_medio.to_numpy(float))
    ax.set_xticks(x,[f'{r.mineral}\n(n={r.n_proyectos})' for r in bymin.itertuples()])
    ax.set_ylabel('IST puntual medio (0–100)')
    ax.set_ylim(0,100)
    ax.set_title('Sensibilidad territorial media de proyectos por mineral')
    for ix,val in enumerate(bymin.ist_medio): ax.text(ix,float(val)+1,f'{val:.1f}',ha='center',fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG/'72_ist_medio_por_mineral.png',dpi=180,bbox_inches='tight')
    plt.close(fig)
    info={'paso':72,'fecha_utc':datetime.now(timezone.utc).isoformat(),
          'estado':'VALIDADO' if srcinfo['estado'].startswith('VALIDADA') else 'PRELIMINAR_FALTA_AUDITORIA_ORIGEN',
          'n_unidades_proyecto':n_unique,'n_filas_proyecto_mineral':n_labels,
          'n_minerales':int(bymin.shape[0]),'n_regiones':int(base.region_espacial.nunique()),
          'fuente_auditoria':srcinfo,
          'cochilco_significado':'Institucion fuente; no equivale a un filtro exclusivo de mineral cobre',
          'advertencias':['No asignar minerales de proyecto a concesiones; catastro no tiene mineral',
                          'Los promedios de grupos pequeños son descriptivos',
                          'Los proyectos COCHILCO son puntos, no superficies de intervención',
                          'Proyectos multiminéricos pueden contabilizarse en varios grupos',
                          'Las distancias de paso 66 sin candidato en 200 km no son distancias exactas']}
    (REPORT/'72_control_analisis_mineral.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    names=[('72_resumen_mineral_ist_componentes.csv','Matriz por mineral'),
           ('72_resumen_region_mineral_ist.csv','Matriz región–mineral'),
           ('72_matriz_proyecto_mineral_region_componentes.csv','Matriz por proyecto'),
           ('72_control_analisis_mineral.json','Control y procedencia')]
    text=['# Resultados por mineral — proyectos seleccionados ENMC', '',
          '> Análisis descriptivo: las localizaciones de proyectos se representan mediante puntos. El IST no mide impactos comprobados.', '',
          '## Universo y procedencia',
          f'- Proyectos únicos: **{n_unique}**; filas proyecto–mineral: **{n_labels}**; minerales: **{len(bymin)}**.',
          f'- Estado de auditoría independiente del origen: **{srcinfo["estado"]}**.',
          '- COCHILCO es la Corporación Chilena del Cobre; su denominación institucional no implica que una cartera evaluada contenga únicamente cobre.',
          '- Dos exclusiones del universo original (carbonato y yeso) se documentan únicamente si existe la tabla original de auditoría.', '',
          '## IST puntual medio según mineral', '',
          '| Mineral | Proyectos | IST medio | Mediana |', '|---|---:|---:|---:|']
    for r in bymin.itertuples():
        text.append(f'| {r.mineral} | {int(r.n_proyectos)} | {r.ist_medio:.2f} | {r.ist_mediana:.2f} |')
    text += ['', '## Gráficos', '',
             '![IST medio por mineral](../../outputs/figures/enmc/72_ist_medio_por_mineral.png)', '',
             '![Aportes por componente](../../outputs/figures/enmc/72_aportes_ist_por_mineral.png)', '',
             '## Tablas y controles', '']
    text.extend(f'- [{label}](../../reports/enmc/{file})' for file,label in names)
    text += ['', '## Limitaciones', '',
             '- Los índices describen proximidad geométrica a elementos sensibles; no son una evaluación de impacto ambiental.',
             '- El índice OA debe interpretarse como huellas candidatas registradas, no como operaciones vigentes confirmadas.',
             '- Las concesiones no informan un mineral identificable; no atribuir superficies concesionadas a un mineral.',
             '- Los grupos con pocos proyectos carecen de robustez inferencial y solo se presentan descriptivamente.',
             '- Las geometrías de proyectos son puntos y las áreas de influencia hipotéticas no equivalen a superficies de intervención.',
             '- Los registros multiminéricos, si existen, se cuentan por cada mineral asociado; el universo único permanece sin duplicación.',
             '']
    (DOC/'72_resultados_por_mineral_ENMC.md').write_text('\n'.join(text),encoding='utf-8')
    print(f'Proyectos unicos: {n_unique}; etiquetas mineral: {n_labels}; estado: {info["estado"]}',flush=True)
    print('Archivos: reports/enmc/72_*; outputs/figures/enmc/72_*; docs/informes/72_resultados_por_mineral_ENMC.md',flush=True)
    print('PASO 72 FINALIZADO',flush=True)

if __name__=='__main__':
    main()
