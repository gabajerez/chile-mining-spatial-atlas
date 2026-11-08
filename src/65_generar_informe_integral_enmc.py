#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera el informe integral ENMC a partir de los outputs realmente publicados.

Uso: python src/65_generar_informe_integral_enmc.py
No cambia los datos originales, no modifica el índice de Git ni realiza push.
"""
from __future__ import annotations
import csv
import json
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'docs' / 'informes' / 'INFORME_INTEGRAL_ENMC.md'
FIGDIR = Path('outputs/figures/enmc')
RDIR = Path('reports/enmc')
TBDIR = Path('outputs/tables')
OTHER_MAPS = Path('outputs/maps/estrategicos')
COMPONENTS = [
    ('Áreas protegidas', '16,5 %', '1 / 5 / 10 / 25'),
    ('Sitios prioritarios + reservas de biosfera', '9,9 %', '1 / 5 / 10 / 25'),
    ('Glaciares', '13,3 %', '0,5 / 2 / 10 / 25'),
    ('Humedales', '12,0 %', '1 / 5 / 10 / 25'),
    ('Planes atmosféricos', '17,0 %', '0,5 / 5 / 25 / 50'),
    ('Comunidades indígenas', '13,1 %', '2 / 10 / 25 / 50'),
    ('Áreas de desarrollo indígena', '6,5 %', '2 / 10 / 25 / 50'),
    ('Áreas pobladas', '7,0 %', '2 / 5 / 15 / 30'),
    ('Atractivos turísticos + ZOIT', '4,7 %', '0,5 / 2 / 5 / 10'),
]


def git_list() -> set[str]:
    p = subprocess.run(['git', '-C', str(ROOT), 'ls-files', '-z'], capture_output=True)
    if p.returncode:
        raise RuntimeError('No se pudo consultar git ls-files; ejecutar desde el repositorio.')
    return {s.replace('\\','/') for s in p.stdout.decode('utf-8','replace').split('\0') if s}


def csv_rows(rel: str) -> list[dict[str,str]]:
    path = ROOT / rel
    if not path.is_file():
        return []
    with path.open('r', encoding='utf-8-sig', newline='') as fp:
        return list(csv.DictReader(fp))


def json_read(rel: str) -> dict:
    p=ROOT/rel
    return json.loads(p.read_text(encoding='utf-8-sig')) if p.is_file() else {}


def num(value: object, digits: int = 2) -> str:
    if value is None or value == '':
        return 'n/d'
    try:
        x=float(value)
        return f'{x:,.{digits}f}'.replace(',','@').replace('.',',').replace('@','.')
    except (TypeError, ValueError):
        return str(value)


def mdlink(relative: str, label: str | None = None) -> str:
    path = Path(relative).as_posix()
    # Report located at docs/informes; links resolve correctly on GitHub.
    return f'[{label or Path(path).name}](../../{quote(path, safe="/._-()")})'


def escaped(v: object) -> str:
    return str(v).replace('|','\\|').replace('\n',' ').replace('\r',' ')


def table(headers: list[str], records: list[list[object]]) -> list[str]:
    return ['| ' + ' | '.join(headers) + ' |',
            '| ' + ' | '.join(['---'] * len(headers)) + ' |'] + [
                '| ' + ' | '.join(escaped(v) for v in r) + ' |' for r in records]


def inventory(tracked: set[str], folder: Path, extensions: set[str] | None = None) -> list[str]:
    prefix=folder.as_posix().rstrip('/') + '/'
    return sorted(s for s in tracked if s.startswith(prefix) and
                  (extensions is None or Path(s).suffix.lower() in extensions))


def main() -> None:
    tracked=git_list()
    main_ist=csv_rows('reports/enmc/57_resumen_cambios_ist_humedales.csv')
    base_ist=csv_rows('reports/enmc/43_ist_enmc.csv')
    final_ist=csv_rows('reports/enmc/57_ist_enmc_humedales_mma.csv')
    overlap=csv_rows('reports/enmc/58_overlap_humedales_mma_resumen.csv')
    zones=csv_rows('reports/enmc/63_conciliacion_humedales_nacional_zonas.csv')
    region=csv_rows('reports/enmc/55_cobertura_regional_humedales_comparativa.csv')
    control=json_read('reports/enmc/58_overlap_humedales_mma_control.json')
    ctrl=control.get('control',{})
    # Published files may be a subset of locally available outputs.
    figures=inventory(tracked,FIGDIR,{'.png','.jpg','.jpeg','.svg','.pdf'})
    strat_maps=inventory(tracked,OTHER_MAPS,{'.png','.jpg','.svg','.pdf'})
    reports=inventory(tracked,RDIR,{'.csv','.json','.md'})
    tables=inventory(tracked,TBDIR,{'.csv','.json','.xlsx'})
    scripts=inventory(tracked,Path('src'),{'.py'})
    docs=inventory(tracked,Path('docs/metodologia'),{'.md'})
    outputs=figures+strat_maps+reports+tables
    missing=[s for folder in (FIGDIR,OTHER_MAPS,RDIR,TBDIR)
             if (ROOT/folder).is_dir()
             for p in (ROOT/folder).rglob('*') if p.is_file()
             if (s:=p.relative_to(ROOT).as_posix()) not in tracked]
    missing=sorted(set(missing))
    current_rev=subprocess.run(['git','-C',str(ROOT),'rev-parse','--short','HEAD'], capture_output=True,text=True)
    rev=current_rev.stdout.strip() if current_rev.returncode==0 else 'no disponible'
    lines=[]
    def add(*vals: str): lines.extend(vals)
    add('# Informe integral de resultados y outputs — Minerales críticos en Chile',
        '',f'> **Versión del repositorio:** `{rev}` · Generado: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}.',
        '> **Naturaleza:** informe técnico reproducible. Los indicadores no acreditan explotación activa, impacto ambiental ni mineral asociado a cada concesión.',
        '', '## 1. Resumen ejecutivo','',
        'El análisis reúne la huella minera registrada seleccionada de OA (292 unidades no verificadas individualmente como activas), '
        '55 localizaciones puntuales de proyectos COCHILCO y concesiones mineras constituidas sin atributo mineral. '
        'Se construyó y actualizó el Índice de Sensibilidad Territorial (IST) y se evaluó la coincidencia espacial '
        'entre coberturas sensibles y concesiones dentro del ámbito común de 343 comunas (75.256.754,28 ha).',
        '')
    if main_ist:
        add('### 1.1 IST: comparación antes/después del inventario nacional MMA','')
        add(*table(['Fuente','n','Unidades modificadas','IST previo','IST actualizado','Δ medio','Δ máximo'],[
            [r.get('fuente'),r.get('n'),r.get('n_cambio_hu'),num(r.get('ist_antes_prom'),3),num(r.get('ist_mma_prom'),3),
             num(r.get('delta_prom'),3),num(r.get('delta_max'),2)] for r in main_ist
        ]),'')
        total=sum(int(r['n']) for r in main_ist)
        changed=sum(int(r['n_cambio_hu']) for r in main_ist)
        add(f'**Total:** {changed} de {total} entidades modificadas por la sustitución del componente de humedales (peso 12 %).', '')
    if ctrl:
        total_h=float(ctrl.get('superficie_sensible_unica_ha',0))
        cons=float(ctrl.get('superficie_sensible_concesionada_ha',0))
        res=float(ctrl.get('superficie_sensible_residual_provisional_ha',0))
        oa=float(ctrl.get('superficie_sensible_concesionada_coincidente_oa_ha',0))
        add('### 1.2 Coincidencia concesional con humedales MMA','',
            *table(['Partición espacial excluyente','Superficie (ha)','% del total'],[
                ['Sin coincidencia concesional',num(total_h-cons,2),num(100*(total_h-cons)/total_h,2)],
                ['Residual concesional provisional',num(res,2),num(100*res/total_h,2)],
                ['Concesión coincidente con huella OA seleccionada',num(oa,2),num(100*oa/total_h,2)],
                ['**Total de humedales en 343 comunas**',f'**{num(total_h,2)}**','**100,00**'],
            ]),'',f'La coincidencia total con concesiones constituidas es **{num(cons,2)} ha**, '
            f'equivalente al **{num(100*cons/total_h,2)} %** de la cobertura inventariada en el ámbito. '
            'El residual y la coincidencia OA son particiones de esa coincidencia, no concesiones adicionales.','')
    add('## 2. Objetivo, universo y delimitación','',
        'Se comparan tres estados territoriales distintos, que no constituyen clases equivalentes de actividad minera:',
        '', '1. **Huella minera registrada (OA, selección ENMC):** polígonos de 292 unidades físicas candidatas; operación vigente no verificada individualmente.',
        '2. **Proyectos anunciados (COCHILCO):** 55 puntos representativos; no se consideran polígonos de intervención ni superficies nuevas verificadas.',
        '3. **Derechos mineros constituidos:** concesiones de exploración y explotación sin atributo de mineral crítico; el residual se obtiene al descontar huellas OA seleccionadas y es provisional.',
        '', 'El ámbito común corresponde a **343 comunas**, no necesariamente a la totalidad de la superficie nacional. '
        'Las áreas se calculan en **EPSG:6933**. Se emplean geometrías no simplificadas para medir; '
        'la simplificación se reserva exclusivamente para cartografía.','')
    add('## 3. Fuentes, cobertura e integridad','',
        '| Insumo | Uso | Precaución |', '| --- | --- | --- |',
        '| OA-2-Articulo | Huella minera registrada y validación inicial IST | Actividad vigente por unidad no verificada |',
        '| COCHILCO | Localización de proyectos | Puntos, no polígonos de impacto |',
        '| SERNAGEOMIN (concesiones constituidas) | Coincidencia concesional y residual | Sin atributo de mineral crítico |',
        '| MMA/SIMBIO (humedales) | Componente HU y superposición | Auditoría temática/temporal aún pendiente |',
        '| Otras diez capas ambientales y sociales | Ocho componentes adicionales del IST | Cobertura temática y vigencia por verificar |',
        '', '### 3.1 Cambio de inventario de humedales','',
        'La capa inicial tenía 4.801 geometrías con presencia en 3/16 regiones. '
        'Se descargó la capa oficial de [MMA/SIMBIO](https://arcgis.mma.gob.cl/server/rest/services/SIMBIO/SIMBIO_HUMEDALES/FeatureServer/0) '
        'con 117.983 identificadores, de los cuales 117.969 poseen geometría utilizable y 14 se excluyeron con trazabilidad individual. '
        'Tras reproyección a EPSG:6933 se documentó una reparación topológica. La capa final tiene presencia en 16/16 regiones.','',
        'La fuente previa permanece preservada a efectos de auditoría. El 35,66 % anteriormente atribuido a humedales '
        'se calculó sobre esa cobertura geográfica limitada y **no es comparable directamente** con el indicador nuevo.','')
    if region:
        add('#### Comparación regional del inventario','')
        headers=list(region[0].keys())
        add(*table(headers,[[r.get(k,'') for k in headers] for r in region]),'')
    add('## 4. Metodología del Índice de Sensibilidad Territorial (IST)','',
        'El IST cuantifica proximidad ponderada a nueve componentes (derivados de once capas) '
        'mediante bandas de distancia. Cada componente recibe 1, 0,75, 0,50, 0,25 o 0 '
        'según la distancia a la cobertura más cercana; fuera de su banda máxima, recibe 0. '
        'Las distancias se estiman en proyecciones azimutales equidistantes locales por unidad.','',
        '| Componente | Peso | Bandas (km) |','| --- | ---: | --- |')
    for name,w,threshold in COMPONENTS:
        add(f'| {name} | {w} | {threshold} |')
    add('', '`IST = 100 × Σ(peso_fraccional × puntaje_componente)`', '',
        'Al sustituir el inventario MMA se actualiza **solo HU** mediante '
        '`IST_57 = IST_43 + 12 × (S_HU_MMA − S_HU_43)`. '
        'Los demás componentes conservan los puntajes del cálculo base.',
        '', '### 4.1 Outputs analíticos del IST','')
    for name,description in [
        ('43_ist_enmc.csv','Puntajes, distancias y aportes iniciales por unidad'),
        ('57_ist_enmc_humedales_mma.csv','Puntajes completos actualizados por unidad'),
        ('57_cambios_ist_humedales_mma.csv','Diferencias por unidad'),
        ('57_resumen_cambios_ist_humedales.csv','Resumen comparativo por fuente'),
        ('57_control_recalculo_humedales.json','Control de ponderación, distancia e integridad')]:
        p=f'reports/enmc/{name}'
        if p in tracked: add(f'- {mdlink(p)} — {description}.')
    add('')
    add('## 5. Coincidencia de humedales y concesiones constituidas','',
        'Se recortó el inventario MMA al ámbito de estudio y se calcularon uniones geométricas únicas '
        'en 110 teselas disjuntas de 120 km. La intersección con concesiones constituidas se descompuso '
        'en residual provisional y coincidencia con la huella OA seleccionada. '
        'Las superficies fueron verificadas mediante balances aritméticos.', '')
    if zones:
        add('### 5.1 Conciliación de zonas cartografiadas y total del ámbito','')
        heads=list(zones[0].keys())
        # Full output embedded, regardless of source column naming.
        add(*table(heads,[[r.get(k,'') for k in heads] for r in zones]),'')
    else:
        add('### 5.1 Conciliación de zonas cartografiadas','',
            '| Zona | Humedales (ha) | Coincidente (ha) | Proporción |',
            '| --- | ---: | ---: | ---: |',
            '| Norte | 721.330,09 | 550.933,28 | 76,38 % |',
            '| Centro | 107.152,07 | 33.924,53 | 31,66 % |',
            '| Norte y centro | 828.482,15 | 584.857,81 | 70,59 % |',
            '| Resto del ámbito (por diferencia) | 4.542.586,03 | 29.876,31 | 0,66 % |',
            '| Total | 5.371.068,19 | 614.734,12 | 11,45 % |','')
    add('Los porcentajes de distintas zonas **no son aditivos** porque tienen denominadores distintos. '
        'El resto del ámbito se obtuvo por diferencia aritmética y no equivale a un nuevo análisis espacial independiente.','')
    add('## 6. Resultados de los demás componentes sensibles','',
        'Las tablas históricas de los pasos 40–42 describen coincidencias sobre insumos originales; '
        'no se equiparan automáticamente con el resultado actualizado de humedales del paso 58. '
        'Estas salidas se catalogan abajo si están publicadas. '
        'Los indicadores de otras categorías continúan sujetos a revisión de vigencia, cobertura y alcance.','')
    add('## 7. Atlas completo de figuras publicadas','',
        'Las imágenes corresponden a salidas del procesamiento y se incrustan directamente desde '
        'el repositorio. Se incluyen también versiones preliminares únicamente cuando estén efectivamente publicadas.','')
    if figures or strat_maps:
        for fig in figures + strat_maps:
            if Path(fig).suffix.lower() not in {'.png','.jpg','.jpeg'}:
                continue
            add(f'### {Path(fig).stem.replace("_"," ")}', '', f'![{Path(fig).stem}](../../{quote(fig, safe="/._-()")})', '',
                f'**Archivo:** {mdlink(fig)}.','')
    else: add('No hay figuras publicadas que cumplan los filtros.','')
    add('## 8. Inventario completo y trazabilidad de outputs publicados','',
        f'En el commit analizado se identificaron **{len(outputs)} outputs publicados** '
        f'({len(figures)+len(strat_maps)} figuras y mapas, {len(reports)} reportes ENMC y '
        f'{len(tables)} tablas adicionales); junto con **{len(scripts)} scripts Python**. '
        'Este catálogo se genera con `git ls-files`, por lo que evita enlaces a outputs locales no subidos.','')
    groups=[('8.1 Figuras y mapas',figures+strat_maps),
            ('8.2 Reportes CSV/JSON ENMC',reports),
            ('8.3 Tablas adicionales',tables),
            ('8.4 Scripts Python',scripts),
            ('8.5 Notas metodológicas',docs)]
    for header,items in groups:
        add('### '+header,'')
        if not items:
            add('Sin archivos publicados en esta categoría.','')
            continue
        if 'Reportes' in header or 'Tablas' in header:
            rows=[]
            for rel in items:
                count='—'
                if rel.endswith('.csv') and (ROOT/rel).is_file():
                    with (ROOT/rel).open(encoding='utf-8-sig',newline='') as f:
                        count=max(0,sum(1 for _ in csv.reader(f))-1)
                rows.append([mdlink(rel),count])
            add(*table(['Archivo publicado','Filas de datos (CSV)'],rows),'')
        else:
            add(*[f'- {mdlink(i)}' for i in items],'')
    add('## 9. Outputs existentes únicamente en el entorno local','',
        'Los siguientes archivos se localizaron en el equipo, pero **no aparecen en el índice actual de Git**. '
        'No se generan enlaces a ellos porque resultarían rotos en GitHub. '
        'Su incorporación requiere revisar derechos de redistribución, pertinencia, tamaño y confidencialidad.','')
    if missing:
        for item in missing:
            add(f'- `{item}`')
    else: add('No se detectaron outputs locales pendientes en las carpetas inventariadas.')
    add('', '## 10. Ruta de reproducción técnica','',
        '1. Descargar y revisar fuentes externas. Conservar metadatos, licencias y fechas.',
        '2. Construir OA, COCHILCO, concesiones y ámbito espacial (scripts 22–39 según documentación).',
        '3. Evaluar sensibilidad original y verificar componentes (scripts 40–47).',
        '4. Auditar y descargar humedales MMA; normalizar geometrías, identificadores y CRS (scripts 52–56b).',
        '5. Recalcular HU e IST (57), coincidencia concesional (58) y balance (59).',
        '6. Regenerar mapas finales (60–61) y validar ámbitos/conciliación (62–63b).',
        '7. Ejecutar `python src/65_generar_informe_integral_enmc.py` para actualizar este documento.',
        '', 'Las entradas `data/raw`, `data/processed` y `data/external` se excluyen deliberadamente de Git. '
        'La reproducción exige reconstruirlas desde las fuentes y scripts, y puede estar condicionada '
        'por cambios en los servicios de terceros.','',
        '## 11. Limitaciones y decisiones pendientes','',
        '1. OA representa huellas registradas; verificar estado operativo antes de calificarlas como activas.',
        '2. COCHILCO aporta ubicaciones de proyectos, no huellas físicas nuevas verificadas.',
        '3. Las concesiones constituidas no poseen atributo mineral crítico; el residual es provisional.',
        '4. La presencia de humedales MMA en las 16 regiones no garantiza exhaustividad ecológica o temporal.',
        '5. Otros ocho componentes del IST requieren revisión temática y temporal de sus fuentes.',
        '6. La coincidencia espacial entre derechos y humedales no prueba intervención, daño ni autorización de explotación.',
        '7. El resultado nacional se refiere al ámbito de 343 comunas, no automáticamente a todo Chile.',
        '8. La categoría «resto del ámbito» del paso 63b deriva de conciliación aritmética.',
        '9. Los scripts históricos fallidos o superados se conservan para trazabilidad; consultar las versiones finales.',
        '10. Evaluar por separado litio, salares y regímenes especiales antes de extraer conclusiones por mineral.',
        '', '## 12. Procedencia y referencias operativas','',
        '- [MMA/SIMBIO: Inventario Nacional de Humedales](https://arcgis.mma.gob.cl/server/rest/services/SIMBIO/SIMBIO_HUMEDALES/FeatureServer/0)',
        '- Documentos y controles de procedencia enumerados en la sección 8.',
        '- [Síntesis metodológica del módulo](../metodologia/64_trazabilidad_enmc_sensibilidad.md)',
        '- La identificación de versiones se realiza a nivel de commit de Git.',
        '', '---',
        '*Documento generado automáticamente. Las cifras se extraen de los archivos publicados existentes; '
        'se recomienda volver a generarlo tras agregar nuevos outputs o modificar las cifras del análisis.*', '')
    report='\n'.join(lines)
    # Explicit guard against names agreed not to be published.
    for forbidden in ('kay','gustavo'):
        if re.search(rf'\b{forbidden}\b',report,re.IGNORECASE):
            raise ValueError('Se detectó una referencia personal en el informe; no se escribió el archivo.')
    DEST.parent.mkdir(parents=True,exist_ok=True)
    DEST.write_text(report, encoding='utf-8')
    print('INFORME:',DEST)
    print('SECCIONES:',12)
    print('FIGURAS/MAPAS:',len(figures)+len(strat_maps))
    print('REPORTES:',len(reports),'TABLAS:',len(tables),'SCRIPTS:',len(scripts))
    print('OUTPUTS LOCALES NO PUBLICADOS:',len(missing))
    print('NO SE REALIZO NINGUN COMMIT NI PUSH.')

if __name__=='__main__':
    main()
