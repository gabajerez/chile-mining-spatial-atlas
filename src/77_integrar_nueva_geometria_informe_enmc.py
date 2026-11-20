#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 77: actualiza sin destruir capítulos el informe integral ENMC.
No publica en Git ni modifica los CSV científicos.
"""
from __future__ import annotations
import csv
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'reports' / 'enmc'
DOCS = ROOT / 'docs' / 'informes'
MAIN = DOCS / 'INFORME_INTEGRAL_ENMC.md'
ANNEX = DOCS / '76_anexo_ist_buffers_minerales_oa.md'
START = '<!-- ENMC_77_NUEVA_GEOMETRIA_INICIO -->'
END = '<!-- ENMC_77_NUEVA_GEOMETRIA_FIN -->'

def require(test, message):
    if not test:
        raise ValueError(message)

def load_csv(name):
    p = REPORTS / name
    require(p.is_file(), f'Falta: {p}')
    with p.open('r', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def num(v):
    return float(v)

def fmt(v, decimal=2):
    s = f'{float(v):,.{decimal}f}'
    return s.replace(',', '\x00').replace('.', ',').replace('\x00', '.')

def main():
    require(MAIN.is_file(), f'Falta informe integral: {MAIN}. Ejecutar paso 74 primero si corresponde.')
    require(ANNEX.is_file(), f'Falta anexo: {ANNEX}')
    for name in [
        '75_auditoria_geometrias_oa.csv',
        '75_control_buffers_mediana_oa.json',
        '76_ist_poligonos_buffers.csv',
        '76_oa_unidades_por_mineral.csv',
        '76_oa_mineral_por_region.csv',
        '76_control_ist_geometrico_minerales_oa.json',
    ]:
        require((REPORTS / name).is_file(), f'Falta resultado o control: {name}')
    src = load_csv('76_resumen_fuentes.csv')
    minrows = load_csv('76_oa_resumen_por_mineral.csv')
    by = {r['fuente']: r for r in src}
    require(set(by) == {'OA_ENMC', 'COCHILCO_ENMC'}, 'Fuentes no coinciden con OA y proyectos')
    require(int(by['OA_ENMC']['count']) == 292, 'No hay 292 OA')
    require(int(by['COCHILCO_ENMC']['count']) == 55, 'No hay 55 proyectos')
    require(len(minrows) == 8, 'No hay 8 grupos minerales OA')
    require(sum(int(r['n_huellas_unicas']) for r in minrows) == 327, 'No se reproducen las 327 asociaciones OA-mineral')
    for r in minrows:
        contrib = sum(num(r['aporte_medio_' + c]) for c in ['AP','SB','GL','HU','AI','CI','AD','PO','TU'])
        require(math.isclose(contrib, num(r['ist_medio']), abs_tol=1e-6), f'No cierra IST: {r["mineral"]}')
    require(abs(num(by['OA_ENMC']['mean']) - 31.052997) < 0.001, 'Media OA inesperada')
    require(abs(num(by['COCHILCO_ENMC']['mean']) - 26.211364) < 0.001, 'Media de proyectos inesperada')
    source_rows = ['| Fuente | Geometría utilizada | Unidades | IST medio | IST mediano |', '|---|---|---:|---:|---:|']
    for k, label, geom in [('OA_ENMC','Huellas OA','Polígono original'), ('COCHILCO_ENMC','Proyectos','Buffer circular de área mediana OA')]:
        r = by[k]
        source_rows.append(f'| {label} | {geom} | {r["count"]} | {fmt(r["mean"],3)} | {fmt(r["median"],3)} |')
    mineral_rows = ['| Mineral OA | Huellas asociadas | IST medio | IST mediano |', '|---|---:|---:|---:|']
    for r in sorted(minrows, key=lambda r: (-int(r['n_huellas_unicas']), r['mineral'])):
        mineral_rows.append(f'| {r["mineral"]} | {r["n_huellas_unicas"]} | {fmt(r["ist_medio"],3)} | {fmt(r["ist_mediana"],3)} |')
    block = '\n'.join([
        START,
        '## Actualización metodológica vigente — polígonos OA y buffers equivalentes (pasos 75b–76)',
        '',
        '**Esta sección reemplaza para la comparación geométrica principal la comparación puntual de los pasos 66–69f.** '
        'Los valores del IST puntual (OA 28,292; proyectos 25,067) se preservan únicamente como sensibilidad metodológica histórica. '
        'Las cifras antiguas de polígonos frente a puntos no deben utilizarse como comparación vigente.',
        '',
        '- **292 polígonos OA:** áreas medidas en EPSG:6933; dos geometrías inválidas reparadas con auditoría.',
        '- **55 proyectos:** buffers circulares hipotéticos ajustados para igualar el área mediana OA (**115,682626 ha**; diámetro equivalente teórico **1.213,638 m**).',
        '- Los buffers **no son huellas de proyecto ni estimaciones de superficie de intervención futura**.',
        '- Aunque las superficies de los buffers son homogéneas, los polígonos OA mantienen sus tamaños y formas originales; esta comparabilidad es parcial.',
        '',
        '### Indicador principal actualizado',
        '',
        *source_rows,
        '',
        f'**Diferencia descriptiva de medias (OA − proyectos): {fmt(num(by["OA_ENMC"]["mean"])-num(by["COCHILCO_ENMC"]["mean"]),3)} puntos.**',
        '',
        '### IST de huellas OA por mineral registrado',
        '',
        *mineral_rows,
        '',
        '**Atención:** 327 asociaciones mineral–huella corresponden a 292 polígonos OA; los grupos minerales son multietiqueta y sus áreas no se suman como total territorial.',
        'Las concesiones constituidas no están atribuidas por mineral en el catastro y los promedios de categorías con pocos registros deben interpretarse con cautela.',
        '',
        '### Respaldos de la actualización',
        '',
        '- [Anexo técnico con aportes de los nueve componentes y limitaciones](76_anexo_ist_buffers_minerales_oa.md)',
        '- [Resultado por fuente](../../reports/enmc/76_resumen_fuentes.csv)',
        '- [Detalle IST por unidad](../../reports/enmc/76_ist_poligonos_buffers.csv)',
        '- [Resultados OA por mineral](../../reports/enmc/76_oa_resumen_por_mineral.csv)',
        '- [Asociaciones mineral–huella](../../reports/enmc/76_oa_unidades_por_mineral.csv)',
        '- [Resultados mineral–región](../../reports/enmc/76_oa_mineral_por_region.csv)',
        '- [Auditoría de geometrías reparadas](../../reports/enmc/75_auditoria_geometrias_oa.csv)',
        '- [Control de equivalencia de buffers](../../reports/enmc/75_control_buffers_mediana_oa.json)',
        '- [Control del IST geométrico](../../reports/enmc/76_control_ist_geometrico_minerales_oa.json)',
        '- [Código de buffers](../../src/75b_buffers_equivalentes_mediana_oa.py) y [código IST por geometría/mineral](../../src/76_ist_poligonos_buffers_y_minerales_oa.py)',
        '', END,
    ])
    text = MAIN.read_text(encoding='utf-8-sig')
    if START in text or END in text:
        require(text.count(START)==1 and text.count(END)==1, 'Marcadores del bloque corruptos')
        a=text.index(START); b=text.index(END)+len(END)
        text=text[:a]+block+text[b:]
    else:
        lines=text.splitlines(keepends=True)
        require(lines and lines[0].lstrip().startswith('# '), 'Encabezado inicial no reconocido')
        # Place above previous content, preserving all previously documented sections.
        text=lines[0]+'\n'+block+'\n\n'+''.join(lines[1:])
    MAIN.write_text(text, encoding='utf-8', newline='\n')
    print('PASO 77 COMPLETO')
    print('Informe actualizado:', MAIN)
    print('Fuentes: OA 292; proyectos 55; minerales OA:', len(minrows))
    print('Bloque único presente:', text.count(START)==1)
    print('Aviso: revisar el resto del informe para rotular como históricos los cuadros metodológicos anteriores.')

if __name__ == '__main__':
    main()
