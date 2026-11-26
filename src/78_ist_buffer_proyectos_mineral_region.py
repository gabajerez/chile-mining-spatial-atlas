#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 78 — IST de proyectos por mineral y región, con geometría BUFFER del paso 76.

No recalcula el IST ni usa las puntuaciones puntuales del paso 72.
El paso 72 se utiliza EXCLUSIVAMENTE para id_fuente, mineral y region_espacial.
Las métricas del IST provienen EXCLUSIVAMENTE del paso 76.

Insumos:
  reports/enmc/76_ist_poligonos_buffers.csv
  reports/enmc/72_matriz_proyecto_mineral_region_componentes.csv
  reports/enmc/76_control_ist_geometrico_minerales_oa.json (si disponible)
Salidas:
  reports/enmc/78_proyectos_mineral_region_ist_buffer_detalle.csv
  reports/enmc/78_resumen_region_mineral_ist_buffer.csv
  reports/enmc/78_resumen_macrozona_mineral_ist_buffer.csv
  reports/enmc/78_resumen_mineral_ist_buffer.csv
  reports/enmc/78_matriz_ist_buffer_macrozona_mineral.csv
  reports/enmc/78_control_ist_buffer_mineral_region.json
  outputs/figures/enmc/78_heatmap_proyectos_mineral_macrozona_buffer.png
  docs/informes/78_resultados_ist_buffer_proyectos_mineral_region.md
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import unicodedata

import numpy as np
import pandas as pd

CODES = ('AP', 'SB', 'GL', 'HU', 'AI', 'CI', 'AD', 'PO', 'TU')

REGION_MACRO = {
    'arica y parinacota': 'Norte',
    'tarapaca': 'Norte',
    'antofagasta': 'Norte',
    'atacama': 'Norte',
    'coquimbo': 'Norte',
    'valparaiso': 'Centro',
    'metropolitana de santiago': 'Centro',
    'metropolitana': 'Centro',
    'region metropolitana': 'Centro',
    'region metropolitana de santiago': 'Centro',
    'libertador general bernardo ohiggins': 'Centro',
    'libertador general bernardo o higgins': 'Centro',
    'ohiggins': 'Centro',
    'o higgins': 'Centro',
    'maule': 'Centro',
    'nuble': 'Centro',
    'biobio': 'Sur',
    'la araucania': 'Sur',
    'araucania': 'Sur',
    'los rios': 'Sur',
    'los lagos': 'Sur',
    'aysen': 'Sur',
    'aysen del general carlos ibanez del campo': 'Sur',
    'magallanes': 'Sur',
    'magallanes y de la antartica chilena': 'Sur',
}


def normalize(value):
    s = unicodedata.normalize('NFKD', str(value).casefold().strip())
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r'[^a-z0-9]+', ' ', s).strip()
    return re.sub(r'\s+', ' ', s)


def macrozona(region):
    key = normalize(region)
    key = re.sub(r'^region (?:de |del |de la |de los )?', '', key).strip()
    # Prefer exact original labels, then remove regional prefix.
    return REGION_MACRO.get(normalize(region), REGION_MACRO.get(key))


def read_csv(path):
    if not path.is_file():
        raise FileNotFoundError(f'Falta insumo: {path}')
    return pd.read_csv(path, encoding='utf-8-sig', dtype={'id_fuente': 'string'})


def make_summary(frame, groups):
    aggs = {
        'n_proyectos': ('id_fuente', 'nunique'),
        'ist_medio': ('IST_100', 'mean'),
        'ist_mediana': ('IST_100', 'median'),
        'ist_minimo': ('IST_100', 'min'),
        'ist_maximo': ('IST_100', 'max'),
    }
    for code in CODES:
        aggs[f'aporte_medio_{code}'] = (f'A_{code}', 'mean')
        aggs[f'puntaje_medio_{code}'] = (f'S_{code}', 'mean')
    out = frame.groupby(groups, dropna=False, sort=True).agg(**aggs).reset_index()
    values = out[[f'aporte_medio_{c}' for c in CODES]].sum(axis=1)
    if not np.allclose(values, out.ist_medio, rtol=0, atol=0.0001):
        raise ValueError('La suma de aportes promedios no reproduce el IST medio')
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    rep = root / 'reports' / 'enmc'
    figdir = root / 'outputs' / 'figures' / 'enmc'
    docs = root / 'docs' / 'informes'
    for d in (rep, figdir, docs):
        d.mkdir(parents=True, exist_ok=True)

    print('=== PASO 78: IST BUFFER DE PROYECTOS POR MINERAL Y REGION ===', flush=True)
    source76 = read_csv(rep / '76_ist_poligonos_buffers.csv')
    source72 = read_csv(rep / '72_matriz_proyecto_mineral_region_componentes.csv')

    required76 = {'fuente', 'id_fuente', 'nombre', 'tipo_geometria_calculo', 'IST_100'}
    required76.update(f'A_{c}' for c in CODES)
    required76.update(f'S_{c}' for c in CODES)
    required72 = {'id_fuente', 'mineral', 'region_espacial'}
    for df, cols, label in ((source76, required76, 'paso 76'), (source72, required72, 'paso 72')):
        missing = cols.difference(df.columns)
        if missing:
            raise ValueError(f'{label}: columnas faltantes: {sorted(missing)}')

    if source76.fuente.value_counts().to_dict() != {'OA_ENMC': 292, 'COCHILCO_ENMC': 55}:
        raise ValueError('Paso 76 no contiene exactamente 292 OA + 55 proyectos')

    buf = source76.loc[source76.fuente.eq('COCHILCO_ENMC')].copy()
    if buf.id_fuente.isna().any() or buf.id_fuente.duplicated().any():
        raise ValueError('Paso 76: identificadores de proyecto nulos o duplicados')
    if not buf.tipo_geometria_calculo.eq('BUFFER_CIRCULAR_MEDIANA_OA').all():
        raise ValueError('El IST del paso 76 no corresponde íntegramente a buffers equivalentes')

    if source72.id_fuente.isna().any() or source72.mineral.isna().any():
        raise ValueError('Paso 72: id o mineral nulo')
    if source72.region_espacial.isna().any():
        raise ValueError('Paso 72: hay proyectos sin región espacial')
    if source72[['id_fuente', 'mineral']].duplicated().any():
        raise ValueError('Paso 72: pares proyecto-mineral repetidos')
    region_by_id = source72.groupby('id_fuente').region_espacial.nunique()
    if region_by_id.max() != 1:
        raise ValueError('Paso 72 asigna regiones contradictorias a un mismo proyecto')
    if set(source72.id_fuente) != set(buf.id_fuente):
        only72 = sorted(set(source72.id_fuente) - set(buf.id_fuente))[:10]
        only76 = sorted(set(buf.id_fuente) - set(source72.id_fuente))[:10]
        raise ValueError(f'IDs incompatibles entre pasos 72 y 76. Solo72={only72}, solo76={only76}')

    for c in ['IST_100'] + [f'A_{k}' for k in CODES] + [f'S_{k}' for k in CODES]:
        buf[c] = pd.to_numeric(buf[c], errors='raise')
        if buf[c].isna().any():
            raise ValueError(f'Paso 76: hay valores nulos en {c}')
    if not buf.IST_100.between(0, 100).all():
        raise ValueError('IST fuera del rango 0–100')
    if not np.allclose(buf[[f'A_{c}' for c in CODES]].sum(axis=1), buf.IST_100, atol=.0001):
        raise ValueError('Paso 76: IST y nueve aportes no coinciden')

    # Solo se importan CLAVES, MINERAL y REGION de la matriz puntual 72.
    taxonomy = source72[['id_fuente', 'mineral', 'region_espacial']].copy()
    fields = ['id_fuente', 'nombre', 'tipo_geometria_calculo', 'area_geometria_ha', 'IST_100']
    fields = [x for x in fields if x in buf] + [f'A_{c}' for c in CODES] + [f'S_{c}' for c in CODES]
    joined = taxonomy.merge(buf[fields], on='id_fuente', how='left', validate='many_to_one', indicator=True)
    if not joined._merge.eq('both').all() or joined.IST_100.isna().any():
        raise ValueError('Falló el cruce de todos los proyectos con el IST buffer')
    joined = joined.drop(columns='_merge')
    joined['macrozona'] = joined.region_espacial.map(macrozona)
    if joined.macrozona.isna().any():
        unknown = joined.loc[joined.macrozona.isna(), 'region_espacial'].drop_duplicates().tolist()
        raise ValueError(f'Hay regiones sin macrozona declarada: {unknown}. Corregir REGION_MACRO y reejecutar.')
    if joined.id_fuente.nunique() != 55:
        raise ValueError('No se preservaron los 55 proyectos')

    # Cada proyecto puede tener varias etiquetas minerales, siempre documentadas.
    reg = make_summary(joined, ['region_espacial', 'mineral'])
    macro = make_summary(joined, ['macrozona', 'mineral'])
    mineral = make_summary(joined, ['mineral'])
    global_mean = float(buf.IST_100.mean())
    if not np.isclose(global_mean, 26.211364, atol=0.02):
        raise ValueError(f'IST medio buffer inesperado: {global_mean:.6f}; verificar versión del paso 76')
    if not np.isclose(np.average(reg.ist_medio, weights=reg.n_proyectos),
                      np.average(joined.IST_100), atol=.0001):
        raise ValueError('Resumen región–mineral no reproduce el agregado de asociaciones')

    detail_path = rep/'78_proyectos_mineral_region_ist_buffer_detalle.csv'
    reg_path = rep/'78_resumen_region_mineral_ist_buffer.csv'
    macro_path = rep/'78_resumen_macrozona_mineral_ist_buffer.csv'
    mineral_path = rep/'78_resumen_mineral_ist_buffer.csv'
    joined.to_csv(detail_path, index=False, encoding='utf-8-sig')
    reg.to_csv(reg_path, index=False, encoding='utf-8-sig')
    macro.to_csv(macro_path, index=False, encoding='utf-8-sig')
    mineral.to_csv(mineral_path, index=False, encoding='utf-8-sig')

    # La mitad 'proyectos' del mapa de calor se alimenta de estas dos matrices:
    # IST medio + cantidad de proyectos, NO resultados del paso 72 puntual.
    order = ['cobre', 'hierro', 'oro', 'plata', 'litio', 'yodo', 'molibdeno', 'tierras_raras']
    minerals = sorted(joined.mineral.unique().tolist(), key=lambda x: (order.index(x) if x in order else 100, x))
    macro_order = ['Norte', 'Centro', 'Sur']
    v = macro.pivot(index='mineral', columns='macrozona', values='ist_medio').reindex(index=minerals, columns=macro_order)
    n = macro.pivot(index='mineral', columns='macrozona', values='n_proyectos').reindex(index=minerals, columns=macro_order)
    wide = pd.DataFrame({'mineral': minerals})
    for area in macro_order:
        wide[f'ist_{area.lower()}'] = v[area].to_numpy()
        wide[f'n_{area.lower()}'] = n[area].to_numpy()
    global_bymin = mineral.set_index('mineral')
    wide['ist_total'] = wide.mineral.map(global_bymin.ist_medio)
    wide['n_total'] = wide.mineral.map(global_bymin.n_proyectos)
    wide.to_csv(rep/'78_matriz_ist_buffer_macrozona_mineral.csv', index=False, encoding='utf-8-sig')

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9.6, max(3.6, 0.48*len(minerals)+1.65)))
    img = ax.imshow(v.to_numpy(dtype=float), cmap='Blues', vmin=0, vmax=60, aspect='auto')
    ax.set_xticks(np.arange(3), macro_order)
    ax.set_yticks(np.arange(len(minerals)), [m.replace('_', ' ').capitalize() for m in minerals])
    for i in range(len(minerals)):
        for j, area in enumerate(macro_order):
            value = v.iloc[i, j]
            if pd.notna(value):
                qty = int(n.iloc[i, j])
                ax.text(j, i, f'{value:.1f} ({qty})', ha='center', va='center', fontsize=9,
                        color=('white' if value >= 33 else '#152b3b'))
            else:
                ax.text(j, i, '—', ha='center', va='center', fontsize=9, color='#62717b')
    ax.set_title('IST medio de proyectos por mineral y macrozona — buffer equivalente', fontsize=11)
    ax.set_xlabel('Macrozona')
    fig.colorbar(img, ax=ax, label='IST medio (0–100)', fraction=.035, pad=.025)
    fig.tight_layout()
    figpath = figdir/'78_heatmap_proyectos_mineral_macrozona_buffer.png'
    fig.savefig(figpath, dpi=320, bbox_inches='tight', facecolor='white')
    plt.close(fig)

    notes = {
        'paso': 78, 'estado': 'COMPLETO',
        'fecha_utc': datetime.now(timezone.utc).isoformat(),
        'ist_fuente': '76_ist_poligonos_buffers.csv',
        'clasificacion_region_fuente': '72_matriz_proyecto_mineral_region_componentes.csv',
        'ist_geometria': 'BUFFER_CIRCULAR_MEDIANA_OA',
        'n_proyectos_unicos': int(joined.id_fuente.nunique()),
        'n_asociaciones_proyecto_mineral': int(len(joined)),
        'n_regiones_con_proyectos': int(joined.region_espacial.nunique()),
        'n_minerales': int(joined.mineral.nunique()),
        'ist_global_proyectos_ponderado_por_unidades': global_mean,
        'cambio_metodologico': 'Puntajes del paso 72 puntual NO usados: se sustituyen por métricas buffer del paso 76',
        'advertencias': [
            'Las áreas circulares de referencia no son huellas reales de proyectos',
            'No sumar conteos si existen proyectos multiminéricos',
            'No calcular el total global como promedio simple de promedios de minerales o regiones',
            'Las regiones son las asignaciones espaciales del paso 69f heredadas por la matriz 72',
            'El IST es una puntuación de sensibilidad, no un porcentaje de superficie afectada',
        ],
    }
    control_path = rep/'78_control_ist_buffer_mineral_region.json'
    control_path.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding='utf-8')

    md = [
        '# IST regional de proyectos por mineral — buffers de área mediana OA', '',
        '**Uso:** sustituir los resultados puntuales de proyectos del paso 72 por esta matriz de superficie. '
        'Mantener el IST poligonal OA del paso 76.', '',
        f'- Proyectos únicos: **{notes["n_proyectos_unicos"]}**.',
        f'- Asociaciones proyecto–mineral: **{notes["n_asociaciones_proyecto_mineral"]}**.',
        f'- IST medio global de proyectos (buffer): **{global_mean:.4f}** puntos.',
        '- Geometría: círculo de superficie equivalente a la mediana de las 292 huellas OA (115,68 ha). '
        'No representa la intervención futura efectiva.',
        '- Taxonomía y región: paso 72; aportes, puntajes e IST: paso 76.', '',
        '## Resultados por mineral', '', mineral.to_markdown(index=False, floatfmt='.3f'), '',
        '## Resultados por macrozona y mineral', '', macro.to_markdown(index=False, floatfmt='.3f'), '',
        '## Productos', '',
        '- [Resumen regional (compatible con estructura 72)](../../reports/enmc/78_resumen_region_mineral_ist_buffer.csv)',
        '- [Resumen macrozonal](../../reports/enmc/78_resumen_macrozona_mineral_ist_buffer.csv)',
        '- [Matriz ancha para mapa de calor](../../reports/enmc/78_matriz_ist_buffer_macrozona_mineral.csv)',
        '- [Resumen por mineral](../../reports/enmc/78_resumen_mineral_ist_buffer.csv)',
        '- [Detalle por proyecto y mineral](../../reports/enmc/78_proyectos_mineral_region_ist_buffer_detalle.csv)',
        '- [Figura del mapa de calor](../../outputs/figures/enmc/78_heatmap_proyectos_mineral_macrozona_buffer.png)',
        '- [Control de integridad](../../reports/enmc/78_control_ist_buffer_mineral_region.json)', '',
        '## Interpretación', '',
        'IST es un índice de proximidad ponderada (0–100), no un porcentaje de impacto. '
        'Los promedios de grupos con n pequeño son descriptivos. '
        'La comparación principal usa polígonos OA frente a buffers equivalentes de los proyectos; '
        'no combina geometrías puntuales con superficies.', '',
    ]
    (docs/'78_resultados_ist_buffer_proyectos_mineral_region.md').write_text('\n'.join(md), encoding='utf-8')

    print(f'Proyectos únicos={notes["n_proyectos_unicos"]} | asociaciones={len(joined)} | IST global buffer={global_mean:.6f}')
    print('Resumen por mineral (buffer):')
    print(mineral[['mineral', 'n_proyectos', 'ist_medio']].to_string(index=False))
    print('Resumen por macrozona y mineral (buffer):')
    print(macro[['macrozona', 'mineral', 'n_proyectos', 'ist_medio']].to_string(index=False))
    print('Región × mineral:', reg_path)
    print('Mapa de calor:', figpath)
    print('PASO 78 FINALIZADO')


if __name__ == '__main__':
    main()
