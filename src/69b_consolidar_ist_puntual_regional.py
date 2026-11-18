#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 69b: matriz regional por fuente y nueve componentes del IST puntual.

Entradas: paso 66 completo, fuente OA/COCHILCO, limites de 16 regiones,
          matriz larga paso 67.
Salidas: CSV regional por componente, CSV por mineral/componente,
         validaciones JSON y dos figuras PNG.

La fuente OA se ubica mediante representative_point() en EPSG:6933, como
el paso 66; COCHILCO mediante su punto original. Las regiones se asignan
espacialmente, nunca por correspondencia informal de nombres.
Las distancias del paso 66 solo están definidas cuando hay candidatos
hasta 200 km: NaN implica distancia no resuelta, no distancia infinita.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports/enmc'
FIG = ROOT / 'outputs/figures/enmc'
BASE = ROOT / 'data/processed/enmc'
REGIONS = ROOT / 'data/processed/regiones_consolidadas.gpkg'
CRS = 'EPSG:6933'
CODES = ['AP','SB','GL','HU','AI','CI','AD','PO','TU']
NAMES = {
  'AP':'Areas protegidas', 'SB':'Sitios y reservas',
  'GL':'Glaciares', 'HU':'Humedales MMA', 'AI':'Planes atmosfericos',
  'CI':'Comunidades indigenas', 'AD':'Areas desarrollo indigena',
  'PO':'Areas pobladas', 'TU':'Turismo'
}
EXPECTED = {'OA_ENMC':292, 'COCHILCO_ENMC':55}


def csv(path):
    if not path.is_file():
        raise FileNotFoundError(path)
    return pd.read_csv(path, encoding='utf-8-sig', dtype={'id_fuente':str})


def make_units():
    oa = gpd.read_file(BASE/'oa_enmc_candidatas.gpkg', engine='pyogrio').to_crs(CRS)
    oa = oa.loc[oa.estado_oa_provisional.eq('CANDIDATA_OPERACION_POR_TIPO')].copy()
    oa['geometry'] = oa.geometry.representative_point()
    oa['fuente'] = 'OA_ENMC'
    oa['id_fuente'] = oa.OBJECTID.astype(str)

    ch = gpd.read_file(BASE/'cochilco_enmc_proyectos.gpkg', engine='pyogrio').to_crs(CRS)
    ident = next((x for x in ('id_proyecto','ID_PROY','ID','OBJECTID') if x in ch), None)
    if ident is None:
        ch['id_calculo'] = range(1,len(ch)+1)
        ident = 'id_calculo'
    ch['fuente'] = 'COCHILCO_ENMC'
    ch['id_fuente'] = ch[ident].astype(str)
    if not ch.geom_type.eq('Point').all():
        raise ValueError('COCHILCO no es estrictamente puntual')
    units = pd.concat([
       oa[['fuente','id_fuente','geometry']],
       ch[['fuente','id_fuente','geometry']]], ignore_index=True)
    units = gpd.GeoDataFrame(units, geometry='geometry', crs=CRS)
    if units[['fuente','id_fuente']].duplicated().any():
        raise ValueError('Identificadores fuente repetidos')
    if units.fuente.value_counts().to_dict() != EXPECTED:
        raise ValueError('Universo OA/COCHILCO distinto de 292/55')
    return units


def main():
    print('=== PASO 69b: MATRICES REGIONAL Y MINERAL DEL IST PUNTUAL ===', flush=True)
    REPORT.mkdir(parents=True,exist_ok=True)
    FIG.mkdir(parents=True,exist_ok=True)
    control_path = REPORT/'66_control_ist_puntual.json'
    if not control_path.exists():
        raise FileNotFoundError(control_path)
    if json.loads(control_path.read_text(encoding='utf-8'))['estado'] != 'COMPLETO':
        raise ValueError('Paso 66 incompleto')
    ist = csv(REPORT/'66_ist_puntual_homologado.csv')
    if ist.fuente.value_counts().to_dict() != EXPECTED:
        raise ValueError('IST no contiene exactamente 292 OA + 55 COCHILCO')
    if ist[['fuente','id_fuente']].duplicated().any():
        raise ValueError('Identificadores duplicados en IST')
    for c in CODES:
        for key in (f'A_{c}',f'S_{c}',f'd_{c}_km'):
            if key not in ist:
                raise ValueError(f'Columna ausente {key}')
    if not np.allclose(ist[[f'A_{c}' for c in CODES]].sum(axis=1),
                       ist.IST_100,atol=1e-4):
        raise ValueError('IST no coincide con suma de aportes')

    regions = gpd.read_file(REGIONS, engine='pyogrio').to_crs(CRS)
    if 'nomreg' not in regions.columns:
        raise ValueError('Capa regional carece de nomreg')
    regions = regions[['nomreg','geometry']].copy()
    regions = regions.loc[regions.geometry.notna() & ~regions.geometry.is_empty]
    units = make_units()
    # Una localizacion puede quedar fuera de las geometrias administrativas,
    # particularmente en costa, islas o por precision de georreferenciacion.
    # No forzar asignacion por proximidad ni inventar una region.
    assigned = gpd.sjoin(units, regions, how='left', predicate='intersects')
    ambiguous = assigned.loc[assigned.duplicated(['fuente','id_fuente'],keep=False)]
    if not ambiguous.empty:
        ambiguous.drop(columns=['geometry'],errors='ignore').to_csv(
            REPORT/'69_puntos_frontera_regional.csv',index=False,encoding='utf-8-sig')
        raise ValueError('Asignacion regional ambigua: revisar 69_puntos_frontera_regional.csv')
    no_region = assigned.loc[assigned.nomreg.isna()].copy()
    if not no_region.empty:
        # Guardar la ubicacion para una investigacion espacial independiente.
        no_region['x_6933'] = no_region.geometry.x
        no_region['y_6933'] = no_region.geometry.y
        no_region_ll = no_region.to_crs('EPSG:4326')
        no_region['lon'] = no_region_ll.geometry.x.to_numpy()
        no_region['lat'] = no_region_ll.geometry.y.to_numpy()
        no_region[['fuente','id_fuente','x_6933','y_6933','lon','lat']].to_csv(
            REPORT/'69_puntos_sin_region.csv',index=False,encoding='utf-8-sig')
        print('ADVERTENCIA: unidades sin asignacion regional espacial:',len(no_region),flush=True)
        print(no_region.groupby('fuente').size().to_string(),flush=True)
        print('Auditoria: reports/enmc/69_puntos_sin_region.csv',flush=True)
    else:
        # Evitar que un CSV de una ejecucion anterior se interprete como vigente.
        old = REPORT/'69_puntos_sin_region.csv'
        if old.exists():
            old.unlink()
    assign = assigned[['fuente','id_fuente','nomreg']].rename(columns={'nomreg':'region_espacial'})
    merged = ist.merge(assign,how='left',on=['fuente','id_fuente'],validate='one_to_one')
    if len(merged)!=347:
        raise ValueError('Error al asociar el universo completo al IST')
    if int(merged.region_espacial.isna().sum()) != len(no_region):
        raise ValueError('Conteo de unidades sin region inconsistente')
    n_regional = int(merged.region_espacial.notna().sum())
    if n_regional + len(no_region) != 347:
        raise ValueError('Balance nacional/regional no cierra')
    if n_regional == 0:
        raise ValueError('Ninguna unidad pudo asociarse a una region; revisar CRS y limites')
    print(f'Asignacion regional comprobada: {n_regional}/347; sin region: {len(no_region)}',flush=True)
    merged.to_csv(REPORT/'69_ist_puntual_unidades_con_region.csv',index=False,encoding='utf-8-sig')

    grouping = ['region_espacial','fuente']
    regional = merged.groupby(grouping,dropna=False).agg(
        n_unidades=('IST_100','size'),
        ist_medio=('IST_100','mean'),
        ist_mediana=('IST_100','median'),
        ist_minimo=('IST_100','min'),
        ist_maximo=('IST_100','max'),
    ).reset_index()
    for c in CODES:
        regional[f'aporte_medio_{c}'] = merged.groupby(grouping)[f'A_{c}'].mean().to_numpy()
        regional[f'puntaje_medio_{c}'] = merged.groupby(grouping)[f'S_{c}'].mean().to_numpy()
    regional.to_csv(REPORT/'69_ist_regional_por_fuente_y_componente.csv',index=False,encoding='utf-8-sig')

    long = csv(REPORT/'67_proyectos_minerales_formato_largo.csv')
    if not set(long.id_fuente).issubset(set(merged.loc[merged.fuente=='COCHILCO_ENMC','id_fuente'])):
        raise ValueError('Matriz mineral tiene identificadores externos')
    if long.duplicated(['id_fuente','mineral']).any():
        raise ValueError('Proyectos/minerales duplicados')
    grouped = long.groupby('mineral')
    mineral = grouped.agg(n_proyectos=('id_fuente','nunique'),ist_medio=('IST_100','mean'),
                          ist_mediana=('IST_100','median')).reset_index()
    for c in CODES:
        mineral[f'aporte_medio_{c}'] = grouped[f'A_{c}'].mean().to_numpy()
    mineral.to_csv(REPORT/'69_ist_mineral_por_componente.csv',index=False,encoding='utf-8-sig')

    # Figura 1: comparacion total fuente OA versus proyectos, nueve componentes.
    compare = merged.groupby('fuente')[[f'A_{c}' for c in CODES]].mean()
    fig,ax = plt.subplots(figsize=(11,4.5))
    pos = np.arange(len(CODES)); width=.36
    for i,(source,row) in enumerate(compare.iterrows()):
        ax.bar(pos+(i-.5)*width,row.to_numpy(),width,label=f'{source} (n={EXPECTED[source]})')
    ax.set_xticks(pos,[NAMES[c] for c in CODES],rotation=40,ha='right')
    ax.set_ylabel('Aporte medio al IST (puntos de 100)')
    ax.set_title('Sensibilidad territorial puntual por componente')
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG/'69_aportes_ist_puntual_oa_cochilco.png',dpi=180)
    plt.close(fig)

    # Figura 2: aporte por mineral, con n visible para evitar sobrerrepresentar grupos pequeños.
    matrix = mineral[[f'aporte_medio_{c}' for c in CODES]].to_numpy()
    fig,ax = plt.subplots(figsize=(11,5.5))
    im=ax.imshow(matrix,aspect='auto',cmap='viridis',vmin=0)
    ax.set_xticks(range(len(CODES)),[NAMES[c] for c in CODES],rotation=40,ha='right')
    ax.set_yticks(range(len(mineral)),[
       f'{r.mineral} (n={r.n_proyectos})' for r in mineral.itertuples(index=False)])
    ax.set_title('Aporte medio por mineral al IST puntual de proyectos COCHILCO')
    fig.colorbar(im,ax=ax,label='Puntos aportados al IST')
    fig.tight_layout()
    fig.savefig(FIG/'69_ist_componentes_por_mineral.png',dpi=180)
    plt.close(fig)

    # NaN en distancia significa fuera de la ventana de candidatos de 200km.
    unmeasured = {c:int(merged[f'd_{c}_km'].isna().sum()) for c in CODES}
    validation = {
       'fecha_utc':datetime.now(timezone.utc).isoformat(),
       'n_unidades_ist':int(len(merged)),
       'n_fuente':{k:int(v) for k,v in merged.fuente.value_counts().items()},
       'n_regiones_representadas':int(merged.region_espacial.nunique()),
       'n_unidades_con_region':n_regional,
       'n_unidades_sin_region':int(len(no_region)),
       'n_sin_region_por_fuente':{k:int(v) for k,v in no_region.fuente.value_counts().items()},
       'advertencia_regional':'Los promedios regionales excluyen unidades sin interseccion con las regiones consolidadas; el promedio nacional conserva las 347 unidades. Revisar 69_puntos_sin_region.csv antes de publicar analisis regional.',
       'n_categorias_minerales':int(len(mineral)),
       'n_filas_proyecto_mineral':int(len(long)),
       'n_distancias_sin_candidato_200km_por_componente':unmeasured,
       'advertencia_distancias':'Distancia no resuelta sin candidato en ventana de 200 km; puntaje igual a cero, no distancia minima verdadera',
       'criterio_regional':'interseccion del punto utilizado para IST con regiones consolidadas',
       'interpretacion':'Promedios descriptivos; no probar equivalencia de ubicacion o estado operativo OA',
    }
    (REPORT/'69_control_consolidacion_ist.json').write_text(
        json.dumps(validation,indent=2,ensure_ascii=False),encoding='utf-8')
    print('Promedios nacionales por fuente:')
    print(merged.groupby('fuente').IST_100.agg(['size','mean']).to_string(),flush=True)
    print('Regiones representadas:',validation['n_regiones_representadas'],flush=True)
    print('Unidades asignadas a region:',n_regional,'| sin region:',len(no_region),flush=True)
    print('Distancias sin candidatos en 200 km:',unmeasured,flush=True)
    print('Reportes: 69_ist_regional_por_fuente_y_componente.csv, 69_ist_mineral_por_componente.csv',flush=True)
    print('Figuras: 69_aportes_ist_puntual_oa_cochilco.png, 69_ist_componentes_por_mineral.png',flush=True)
    print('PASO 69b FINALIZADO (regional provisional si hay unidades sin region)',flush=True)

if __name__=='__main__':
    main()
