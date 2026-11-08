#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 63: conciliación trazable de superposición MMA nacional vs zonas 61.

No modifica geodatos ni presupone que el remanente corresponda exclusivamente
al sur: la diferencia se interpreta como 'resto no cartografiado' solo si
los balances son compatibles. El remanente es una resta de resúmenes, no
una intersección independiente; las cifras zonales son preliminares.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REP = ROOT / 'reports' / 'enmc'
OUT = ROOT / 'docs' / 'metodologia'
THRESHOLD_HA = 0.02


def require(condition: bool, message: str):
    if not condition:
        raise ValueError(message)


def main():
    print('=== PASO 63: CONCILIACION HUMEDALES NACIONAL / ZONAS ===', flush=True)
    a = pd.read_csv(REP / '58_overlap_humedales_mma_resumen.csv', encoding='utf-8-sig')
    b = pd.read_csv(REP / '61_control_overlap_cartografico_mma.csv', encoding='utf-8-sig')
    audit = json.loads((REP / '62_auditoria_ambitos_58_61.json').read_text(encoding='utf-8'))
    require(len(a) == 1, 'Se esperaba una fila nacional del paso 58')
    require('ambito_nacional_comunal_ha' in audit and 'norte_centro_solapamiento_ha' in audit,
            'El control 62 no contiene los campos esperados')
    require(float(a.iloc[0]['n_comunas_ambito']) == 343, 'El ámbito nacional no contiene 343 comunas')
    require(float(a.iloc[0]['n_teselas']) == 110, 'El paso 58 no contiene 110 teselas')
    cols = {'zona','componente','sensible_ha','concesionada_ha','residual_ha',
            'coincidente_oa_ha','no_concesionada_ha','error_balance_m2'}
    require(cols.issubset(b.columns), f'Faltan columnas 61: {cols-set(b.columns)}')
    require(not b.duplicated(['zona','componente']).any(), 'Filas duplicadas en paso 61')
    require(float(audit['norte_centro_solapamiento_ha']) <= 0.02,
            'Las zonas norte y centro se superponen significativamente')
    require(b['error_balance_m2'].abs().max() < 1.,
            'Alguna zona del paso 61 no cierra su balance de superficies')
    d = b[b['componente'].astype(str).str.lower() == 'humedales'].copy()
    require(set(d['zona']) == {'norte','centro'} and len(d) == 2,
            'Se esperaban exactamente dos zonas de humedales')
    ca = a.iloc[0]
    national = {
        'humedales_ha': float(ca['superficie_sensible_unica_ha']),
        'concesionada_ha': float(ca['superficie_sensible_concesionada_ha']),
        'residual_ha': float(ca['superficie_sensible_residual_provisional_ha']),
        'oa_ha': float(ca['superficie_sensible_concesionada_coincidente_oa_ha']),
    }
    records = []
    for _, r in d.iterrows():
        h,c,res,oa,libre = (float(r[k]) for k in
                             ('sensible_ha','concesionada_ha','residual_ha','coincidente_oa_ha','no_concesionada_ha'))
        require(all(v >= -THRESHOLD_HA for v in (h,c,res,oa,libre)),
                'Se detectaron superficies negativas')
        require(abs(h-(libre+res+oa)) <= THRESHOLD_HA,
                f'Balance no cierra en {r.zona}')
        require(abs(c-(res+oa)) <= THRESHOLD_HA,
                f'Concesión no equivale a residual + OA en {r.zona}')
        records.append({'ambito': str(r.zona), 'humedales_ha':h,'concesionada_ha':c,
                        'residual_ha':res,'oa_ha':oa,'sin_concesion_ha':libre,
                        'porcentaje_concesionado':100*c/h if h else None,
                        'origen':'61_interseccion_zonal'})
    totals={k:sum(r[k] for r in records) for k in ('humedales_ha','concesionada_ha','residual_ha','oa_ha')}
    remainder={k:national[k]-totals[k] for k in totals}
    require(all(v >= -THRESHOLD_HA for v in remainder.values()),
            f'Sumas zonales exceden nacional: {remainder}')
    require(abs(national['concesionada_ha']-(national['residual_ha']+national['oa_ha'])) < THRESHOLD_HA,
            'Balance nacional constituidas / residual / OA no cierra')
    for name, obj, origin in (
        ('norte_y_centro', totals, 'suma_intersecciones_zonales'),
        ('resto_no_cartografiado', remainder, 'diferencia_nacional_menos_zonas'),
        ('ambito_343_comunas', national, '58_interseccion_nacional')):
        h,c,res,oa=(obj[k] for k in ('humedales_ha','concesionada_ha','residual_ha','oa_ha'))
        records.append({'ambito':name,'humedales_ha':h,'concesionada_ha':c,
                        'residual_ha':res,'oa_ha':oa,'sin_concesion_ha':h-c,
                        'porcentaje_concesionado':100*c/h if h else None,'origen':origin})
    # The subtraction confirms compatibility but is not an independently recomputed spatial overlay.
    REP.mkdir(parents=True,exist_ok=True)
    OUT.mkdir(parents=True,exist_ok=True)
    csv=REP/'63_conciliacion_humedales_nacional_zonas.csv'
    js=REP/'63_control_conciliacion_humedales.json'
    md=OUT/'63_conciliacion_humedales_nacional_zonas.md'
    pd.DataFrame(records).to_csv(csv,index=False,encoding='utf-8-sig',float_format='%.8f')
    control={
        'paso':63,'utc':datetime.now(timezone.utc).isoformat(),
        'estado':'BALANCE_ARITMETICO_COMPATIBLE_REMANENTE_NO_RECALCULADO',
        'ambito':'343 comunas; zonas norte y centro contenidas sin solapamiento significativo',
        'fuentes':['58_overlap_humedales_mma_resumen.csv',
                   '61_control_overlap_cartografico_mma.csv',
                   '62_auditoria_ambitos_58_61.json'],
        'remainder':remainder,
        'advertencias':[
            'El resto es una diferencia aritmetica; no una nueva interseccion espacial.',
            'No interpretar resto como una region especifica sin auditar su geometria.',
            'Derechos mineros sin atributo de mineral; residual provisional por seleccion OA.',
            'La coincidencia espacial no evidencia actividad ni impacto ambiental.',
            'Las areas por zona deben validarse independientemente si se requiere igualdad espacial estricta.'
        ]}
    js.write_text(json.dumps(control,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Paso 63 — Conciliación entre cobertura nacional y zonas cartografiadas','',
           'El inventario MMA se analiza en el ámbito común de 343 comunas. El norte y la zona central están contenidos en dicho ámbito según el paso 62.','',
           '| Ámbito | Humedales (ha) | Concesionada (ha) | Concesionada (%) |','|---|---:|---:|---:|']
    for r in records:
        lines.append(f"| {r['ambito']} | {r['humedales_ha']:,.2f} | {r['concesionada_ha']:,.2f} | {r['porcentaje_concesionado']:.2f} |")
    lines += ['', '## Alcance y precauciones', '',
              'Las cifras del «resto no cartografiado» resultan de restar los resúmenes zonales al resultado nacional. No equivalen a una superposición espacial independiente; no deben asignarse automáticamente a una región ni utilizarse para afirmar cierre espacial exacto.','',
              'Las concesiones mineras constituidas no identifican el mineral. El residual es provisional y las huellas OA no acreditan operación vigente. La superposición no equivale a impacto ambiental.','',
              '## Archivos de referencia', '',
              '- `reports/enmc/58_overlap_humedales_mma_resumen.csv`',
              '- `reports/enmc/61_control_overlap_cartografico_mma.csv`',
              '- `reports/enmc/62_auditoria_ambitos_58_61.json`','']
    md.write_text('\n'.join(lines),encoding='utf-8')
    for r in records:
        print(f"  {r['ambito']}: H={r['humedales_ha']:,.2f} ha, C={r['concesionada_ha']:,.2f} ha, coincidencia={r['porcentaje_concesionado']:.2f}%", flush=True)
    print('Archivos:',csv,js,md,sep='\n  ',flush=True)
    print('PASO 63 FINALIZADO',flush=True)

if __name__=='__main__':
    main()
