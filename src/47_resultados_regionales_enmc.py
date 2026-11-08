#!/usr/bin/env python3
"""Paso 47: normalización, auditoría y figuras regionales del IST ENMC.

Entradas: reports/enmc/46_{ist_por_region,unidades_ist_regionalizadas,aportes_promedio_ist}.csv
Salidas: reports/enmc/47_* (CSV, Markdown y PNG).
No modifica archivos originales ni altera los resultados del IST.
"""
from __future__ import annotations
import argparse
import re
import unicodedata
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

NAMES = {
    'arica y parinacota': 'Arica y Parinacota',
    'tarapaca': 'Tarapacá', 'antofagasta': 'Antofagasta', 'atacama': 'Atacama',
    'coquimbo': 'Coquimbo', 'valparaiso': 'Valparaíso',
    'metropolitana de santiago': 'Metropolitana', 'metropolitana': 'Metropolitana',
    'libertador bernardo ohiggins': "O’Higgins",
    'libertador general bernardo ohiggins': "O’Higgins",
    'ohiggins': "O’Higgins", 'maule': 'Maule', 'nuble': 'Ñuble',
    'biobio': 'Biobío', 'bio bio': 'Biobío', 'araucania': 'La Araucanía',
    'la araucania': 'La Araucanía', 'los rios': 'Los Ríos', 'rios': 'Los Ríos', 'los lagos': 'Los Lagos', 'lagos': 'Los Lagos',
    'aysen': 'Aysén', 'aysen del general carlos ibanez del campo': 'Aysén',
    'magallanes y la antartica chilena': 'Magallanes',
    'magallanes': 'Magallanes',
}
COMPONENTS = {
    'A_AP': 'Áreas protegidas', 'A_SB': 'Sitios prioritarios y reservas',
    'A_GL': 'Glaciares', 'A_HU': 'Humedales',
    'A_AI': 'Planes atmosféricos', 'A_CI': 'Comunidades indígenas',
    'A_AD': 'Áreas de desarrollo indígena', 'A_PO': 'Áreas pobladas',
    'A_TU': 'Atractivos y zonas turísticas'
}
EXPECTED = {'OA_ENMC': 292, 'COCHILCO_ENMC': 55}

def norm(s):
    s = ''.join(c for c in unicodedata.normalize('NFKD', str(s)) if not unicodedata.combining(c))
    s = s.lower().replace('’', '').replace("'", '')
    s = re.sub(r'^region\s+(?:de\s+la\s+|de\s+los\s+|de\s+las\s+|del\s+|de\s+)?', '', s)
    return ' '.join(re.sub(r'[^a-z0-9 ]', ' ', s).split())

def normalize_region(x):
    key = norm(x)
    if key not in NAMES:
        raise ValueError(f'Nombre regional sin homologación: {x!r} -> {key!r}')
    return NAMES[key]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    base = root / 'reports' / 'enmc'
    f_reg = base / '46_ist_por_region.csv'
    f_units = base / '46_unidades_ist_regionalizadas.csv'
    f_comp = base / '46_aportes_promedio_ist.csv'
    for file in (f_reg, f_units, f_comp):
        if not file.exists():
            raise FileNotFoundError(file)
    reg = pd.read_csv(f_reg, encoding='utf-8-sig')
    units = pd.read_csv(f_units, encoding='utf-8-sig')
    comp = pd.read_csv(f_comp, encoding='utf-8-sig')

    required_units = {'fuente', 'id_fuente', 'nombre', 'region', 'IST_100'}
    if not required_units.issubset(units.columns):
        raise ValueError(f'Faltan columnas de unidades: {required_units-set(units.columns)}')
    if units.duplicated(['fuente', 'id_fuente']).any():
        raise ValueError('Identificadores duplicados por fuente')
    if units[['fuente', 'id_fuente', 'nombre', 'region', 'IST_100']].isna().any().any():
        raise ValueError('Valores faltantes en unidades')
    if not units['IST_100'].between(0, 100).all():
        raise ValueError('IST fuera de 0-100')
    observed = units.groupby('fuente').size().to_dict()
    if observed != EXPECTED:
        raise ValueError(f'Cantidad inesperada por fuente: {observed}; esperado {EXPECTED}')
    units['region_normalizada'] = units['region'].map(normalize_region)
    reg['region_normalizada'] = reg['region'].map(normalize_region)

    check = units.groupby(['fuente','region_normalizada'],as_index=False).agg(
        n=('IST_100','size'), media=('IST_100','mean'),
        mediana=('IST_100','median'), minimo=('IST_100','min'), maximo=('IST_100','max'))
    original = reg[['fuente','region_normalizada','n','media','mediana','minimo','maximo']]
    merged = check.merge(original,on=['fuente','region_normalizada'],how='outer',suffixes=('_calc','_orig'),indicator=True)
    if not (merged['_merge']=='both').all():
        raise ValueError('Diferencias entre conjuntos regionales del CSV y unidades')
    for field in ['n','media','mediana','minimo','maximo']:
        if (merged[f'{field}_calc'] - merged[f'{field}_orig']).abs().max() > (0 if field=='n' else 1e-6):
            raise ValueError(f'Discrepancia de {field} entre unidades y resumen regional')

    comp_cols = list(COMPONENTS)
    if not set(comp_cols).issubset(comp.columns):
        raise ValueError('Faltan aportes del IST')
    means = units.groupby('fuente').IST_100.mean()
    for _, row in comp.iterrows():
        if abs(row[comp_cols].sum()-means.loc[row['fuente']])>1e-6:
            raise ValueError(f'Los aportes no suman IST medio de {row["fuente"]}')

    long = check.sort_values(['fuente','media'],ascending=[True,False]).copy()
    long['advertencia_n_pequeno'] = long.n < 5
    long.to_csv(base/'47_ist_regiones_homologadas.csv',index=False,encoding='utf-8-sig')
    units.to_csv(base/'47_unidades_regiones_homologadas.csv',index=False,encoding='utf-8-sig')
    aportes = comp.melt(id_vars=['fuente'], value_vars=comp_cols, var_name='codigo', value_name='aporte_promedio_puntos')
    aportes['componente'] = aportes['codigo'].map(COMPONENTS)
    aportes.to_csv(base/'47_aportes_ist_largo.csv',index=False,encoding='utf-8-sig')

    plt.rcParams.update({'font.size': 10})
    for source, label in [('OA_ENMC','OA-ENMC: candidatos a operación'),('COCHILCO_ENMC','COCHILCO-ENMC: proyectos puntuales')]:
        d=long[long.fuente==source].sort_values('media')
        fig,ax=plt.subplots(figsize=(10, max(5, 0.48*len(d)+1.5)))
        bars=ax.barh(d.region_normalizada,d.media)
        for bar,n,v in zip(bars,d.n,d.media):
            ax.text(bar.get_width()+0.6, bar.get_y()+bar.get_height()/2, f'{v:.1f} (n={n})',va='center',fontsize=9)
        ax.set_xlim(0,max(100,d.media.max()+20))
        ax.set_xlabel('IST medio (puntos sobre 100)')
        ax.set_title(label+' — promedio regional descriptivo')
        ax.grid(axis='x',alpha=0.2)
        ax.set_axisbelow(True)
        fig.text(.01,.01,'n<5: interpretar con especial cautela. Universo filtrado ENMC; no representa toda la región.',fontsize=8)
        fig.tight_layout(rect=(0,0.045,1,1))
        out=base/f'47_ist_regional_{source.lower()}.png'
        fig.savefig(out,dpi=200,bbox_inches='tight')
        plt.close(fig)

    fig,ax=plt.subplots(figsize=(11,6))
    pivot=aportes.pivot(index='componente',columns='fuente',values='aporte_promedio_puntos')
    pivot=pivot.loc[[COMPONENTS[x] for x in comp_cols]].sort_values('OA_ENMC')
    y=range(len(pivot))
    ax.barh([v-0.2 for v in y],pivot['OA_ENMC'],height=.38,label='OA-ENMC')
    ax.barh([v+0.2 for v in y],pivot['COCHILCO_ENMC'],height=.38,label='COCHILCO-ENMC')
    ax.set_yticks(list(y),pivot.index)
    ax.set_xlabel('Aporte promedio al IST (puntos)')
    ax.set_title('Contribución promedio de los nueve componentes')
    ax.legend()
    ax.grid(axis='x',alpha=.2)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(base/'47_aportes_componentes_ist.png',dpi=200,bbox_inches='tight')
    plt.close(fig)

    with (base/'47_resumen_regional_ist.md').open('w',encoding='utf-8') as f:
        f.write('# Resultados regionales del IST — ENMC (preliminar)\n\n')
        f.write('Universo: 292 polígonos OA candidatos a operación y 55 puntos representativos COCHILCO. '
                'La regionalización y el IST son válidos para las geometrías y fuentes usadas, pero no confirman estado operativo '
                'ni huellas nuevas de proyectos. Medias regionales descriptivas, no indicadores de toda la región.\n\n')
        for source in ['OA_ENMC','COCHILCO_ENMC']:
            f.write(f'## {source}\n\n| Región | n | IST medio | Mediana |\n|---|---:|---:|---:|\n')
            for _,r in long[long.fuente==source].iterrows():
                f.write(f'| {r.region_normalizada} | {r.n} | {r.media:.2f} | {r.mediana:.2f} |\n')
            f.write('\n')
        f.write('**Limitaciones:** No sumar áreas sensibles superpuestas; las concesiones son derechos, '
                'no prueba de extracción o impacto. n pequeños requieren especial cautela. '
                'Las fuentes OA y COCHILCO contienen unidades distintas y no deben fusionarse en una media única.\n')

    print('=== PASO 47 COMPLETADO ===')
    print('Unidades:',len(units),'| Fuentes:',observed)
    print('Regiones:',long.groupby('fuente').size().to_dict())
    print('IST promedio:',means.round(4).to_dict())
    print('Filas regionales con n<5:',int(long.advertencia_n_pequeno.sum()))
    print('Archivos 47_* creados en:',base)

if __name__=='__main__':
    main()
