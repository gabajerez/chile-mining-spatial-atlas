#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 74: informe integral ENMC basado en archivos locales validados.

No cambia resultados cientificos, no modifica Git, no publica datos.
Genera docs/informes/INFORME_INTEGRAL_ENMC.md y un manifiesto de outputs.
Aborta si faltan controles clave o si los universos no cuadran.
"""
from __future__ import annotations
import csv, json, math, re, subprocess
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
R = ROOT/'reports/enmc'
D = ROOT/'docs/informes'
O = ROOT/'outputs/figures/enmc'
REQUIRED = [
 '66_ist_puntual_homologado.csv',
 '69_ist_regional_por_fuente_y_componente.csv',
 '69_ist_puntual_unidades_con_region.csv',
 '70_overlap_regional_componentes.csv',
 '70_resumen_nacional_por_componente.csv',
 '71_puntos_sensibles_coincidencia_regional.csv',
 '71_control_puntos_sensibles.json',
 '72_resumen_mineral_ist_componentes.csv',
 '72_matriz_proyecto_mineral_region_componentes.csv',
 '72_resumen_region_mineral_ist.csv',
 '72_control_analisis_mineral.json',
 '73_escenarios_por_mineral_ambito.csv',
 '73_control_escenarios_por_mineral.json',
]
COMP = {'AP':'Áreas protegidas','SB':'Sitios prioritarios + reservas de biosfera',
        'GL':'Glaciares','HU':'Humedales MMA','AI':'Planes atmosféricos',
        'CI':'Comunidades indígenas (puntos)','AD':'Áreas de desarrollo indígena',
        'PO':'Áreas pobladas','TU':'Zonas turísticas (polígonos)'}

def rows(name):
    with (R/name).open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))
def read_json(name): return json.loads((R/name).read_text(encoding='utf-8-sig'))
def number(v):
    try: return float(v)
    except (TypeError, ValueError): return float('nan')
def fmt(v,dec=2):
    x=number(v)
    if not math.isfinite(x):return 'n/a'
    return f'{x:,.{dec}f}'.replace(',','\x00').replace('.',',').replace('\x00','.')
def txt(v):return str(v).replace('|','\\|').replace('\n',' ').replace('\r',' ')
def tab(headers, records):
    out=['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']
    return '\n'.join(out+['| '+' | '.join(map(txt,r))+' |' for r in records])
def link(path,label=None):
    rel=path.relative_to(ROOT).as_posix()
    return f'[{label or path.name}](../../{rel})'
def figure(p,caption):
    return f'![{caption}](../../{p.relative_to(ROOT).as_posix()})\n\n*{caption}.*'
def require(c,msg):
    if not c: raise ValueError(msg)

def main():
    absent=[str(R/p) for p in REQUIRED if not (R/p).is_file()]
    require(not absent,'Faltan archivos del calculo: '+', '.join(absent))
    ist=rows('66_ist_puntual_homologado.csv')
    u=rows('69_ist_puntual_unidades_con_region.csv')
    regional=rows('69_ist_regional_por_fuente_y_componente.csv')
    overlap=rows('70_overlap_regional_componentes.csv')
    nat=rows('70_resumen_nacional_por_componente.csv')
    pts=read_json('71_control_puntos_sensibles.json')
    mineral=rows('72_resumen_mineral_ist_componentes.csv')
    projects=rows('72_matriz_proyecto_mineral_region_componentes.csv')
    mr=rows('72_resumen_region_mineral_ist.csv')
    c72=read_json('72_control_analisis_mineral.json')
    scen=rows('73_escenarios_por_mineral_ambito.csv')
    c73=read_json('73_control_escenarios_por_mineral.json')
    require(len(ist)==347 and len(u)==347,'Universo IST no es 347')
    require(sum(x['fuente']=='OA_ENMC' for x in ist)==292,'OA n !=292')
    require(sum(x['fuente']=='COCHILCO_ENMC' for x in ist)==55,'COCHILCO n !=55')
    require(all(x.get('region_espacial','').strip() for x in u),'Existen unidades sin region')
    require(len(overlap)==144 and len(nat)==9,'Paso 70 incompleto')
    require(len(projects)==55 and len(mineral)==6,'Minerales incompletos o proyectos repetidos')
    require(len(scen)==24,'Faltan escenarios de radio/mineral')
    require(c73.get('estado')=='COMPLETO','Control 73 no completo')
    require('VALID' in str(c72.get('estado','')).upper(),'Auditoria 72 no validada')
    hu=next(x for x in nat if x['componente']=='HU')
    require(abs(number(hu['coincidente_ha'])-614734.121057)<0.1,'Humedales no concilian con paso 58')
    mean=lambda source: sum(number(v['IST_100']) for v in ist if v['fuente']==source)/sum(v['fuente']==source for v in ist)
    mean_oa,mean_co=mean('OA_ENMC'),mean('COCHILCO_ENMC')
    require(abs(mean_oa-28.291952)<0.02 and abs(mean_co-25.066818)<0.02,'IST nacional difiere del log validado')
    # Prevent misleading link output: list only curated outputs that the publishing command stages.
    public_reports=[p for p in sorted(R.iterdir()) if p.is_file() and p.suffix.lower() in ('.csv','.json')
                    and re.match(r'^(5[4-9]|6[0-9]|7[0-3])[a-z]?_',p.name)
                    and not any(s in p.name.lower() for s in ('checkpoint','prueba'))]
    # Audit individual points may contain sensitive attributes; explicitly not publish those.
    public_reports=[p for p in public_reports if not any(x in p.name for x in
        ('71_registros_puntuales_individuales','71_puntos_sin_region_o_multirregion'))]
    published_figures=[p for p in sorted(O.glob('*.png')) if re.match(r'^(48b|49c|59|60|61|69|72|73)_',p.name) and p.stat().st_size<15_000_000]
    # Never link SVG; they were intentionally removed from Git due to size.
    D.mkdir(parents=True,exist_ok=True)
    lines=[]
    def add(*args):lines.extend(args)
    add('# Informe integral — Atlas de minerales críticos y sensibilidad territorial',
        '',f'> **Actualizado desde outputs locales:** {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}. ',
        '> **Alcance:** 343 comunas, 16 regiones, 347 unidades IST, 11 capas para 9 componentes. '
        'Los indicadores describen proximidad y coincidencias espaciales, no impacto ambiental efectivo.',
        '', '## 1. Resumen ejecutivo',
        '',f'Se analizaron **292 huellas OA candidatas**, **55 proyectos localizados en puntos** y '
        f'**83.522 concesiones constituidas**. El IST **homologado por localización puntual** alcanza '
        f'**{fmt(mean_oa)}** puntos en OA y **{fmt(mean_co)}** en proyectos. '
        'La asignación regional está resuelta para 347/347 registros. '
        'La geometría OA describe huella registrada, no necesariamente una faena actualmente operativa. '
        'Los puntos COCHILCO no son superficies verificadas de proyecto.',
        '', '## 2. Fuentes, unidades y decisiones metodológicas',
        '', '- **OA:** 292 polígonos; un punto representativo interior para el IST homologado. La huella original permanece para el análisis geométrico complementario.',
        '- **Cartera de proyectos integrada:** 55 localizaciones puntuales y clasificación mineral contrastada con un inventario histórico de 57 registros (55 incluidos, 2 excluidos). COCHILCO es el nombre de la institución, no una clasificación mineral.',
        '- **Concesiones:** 83.522 registros; la unión de concesiones dentro del ámbito cubre 16.239.453,84 ha, sin atributo que permita adjudicarlas a un mineral específico.',
        '- **Ámbito:** 343 comunas (75.256.754,28 ha); EPSG:6933 para áreas y proyección métrica local para distancias.',
        '- **IST:** nueve componentes ponderados y 11 capas. El índice poligonal inicial **no es comparable directamente** con el puntual y se conserva únicamente como resultado complementario.',
        '- **Humedales:** capa nacional MMA/SIMBIO de 117.969 geometrías útiles, sustitución del inventario anterior incompleto.',
        '- **Limitaciones:** estatus operativo OA no verificado individualmente; exactitud espacial de puntos y vigencia de fuentes no auditadas completamente; sin polígonos de intervención futuros verificados.',
        '', '## 3. IST puntual homologado OA–proyectos',
        '',tab(['Fuente','n','IST medio (0–100)','Criterio geométrico'],[
          ['OA',292,fmt(mean_oa,4),'Punto representativo interior'],
          ['Proyectos',55,fmt(mean_co,4),'Punto fuente']]),
        '', 'Las distancias que superan la ventana de búsqueda de 200 km no se interpretan como distancias exactas; reciben cero cuando están fuera de la banda máxima de puntaje. '
        'La diferencia entre las medias es descriptiva y no demuestra un efecto causal ni equivalencia sustantiva entre las poblaciones.',
        '', '### 3.1 IST regional por fuente',
        '',tab(['Región','Fuente','n','IST medio'],[[x['region_espacial'],x['fuente'],x['n_unidades'],fmt(x['ist_medio'])] for x in regional]),
        '', 'La unidad OA 162 (Puerto Caldera, 1,18 ha) se asigna administrativamente a Atacama por intersección de su polígono y atributo original; '
        'el punto estaba a aproximadamente 3 m del límite digital. No se movió el punto ni se alteró su IST.',
        '', '## 4. Coincidencia concesional por componente',
        '', 'Los componentes poligonales se expresan como porcentaje de la **superficie de cada capa** que coincide con concesiones. '
        'No deben sumarse áreas de componentes diferentes por posibles superposiciones.',
        '',tab(['Componente','Superficie sensible (ha)','Coincidente (ha)','Coincidencia superficial'],[
          [COMP.get(x['componente'],x['componente']),fmt(x['sensible_ha']),fmt(x['coincidente_ha']),fmt(x['porcentaje'])+' %' if math.isfinite(number(x['porcentaje'])) else 'No aplica (puntos)']
          for x in nat]),
        '', '### 4.1 Componentes representados por puntos',
        '', 'Para comunidades indígenas y atractivos turísticos se cuantifica la proporción de **registros puntuales** localizados dentro de la unión concesional; '
        'no corresponde a superficie ni a afectación material.' )
    summaries=pts.get('resumen',[])
    add('',tab(['Capa','Registros en ámbito','Coincidentes','Porcentaje de registros'],[
        [x.get('componente',''),x.get('puntos_en_ambito',''),x.get('coincidentes_concesion',''),fmt(x.get('porcentaje_registros_en_concesion'))+' %'] for x in summaries]),
        '', '### 4.2 Matriz regional',
        '', 'Las 144 combinaciones (16 regiones × 9 componentes) se encuentran en '+link(R/'70_overlap_regional_componentes.csv')+'. '
        'El agregado de humedales reproduce 614.734,121 ha de coincidencia con concesiones (11,4453 %); '
        'la diferencia de 0,006 ha en superficie sensible frente al paso 58 es de precisión geométrica.',
        '', '## 5. Análisis por mineral de proyectos',
        '', 'Clasificación contrastada registro a registro con el inventario histórico. '
        'Los resultados describen proyectos, no composición mineral de las concesiones.',
        '',tab(['Mineral','Proyectos','IST medio','Mediana IST'],[
          [x['mineral'],x['n_proyectos'],fmt(x['ist_medio']),fmt(x['ist_mediana'])] for x in mineral]),
        '', 'Los nueve aportes y puntajes de cada grupo, además de la tabla regional por mineral, se adjuntan como CSV. '
        'Los grupos con uno, dos o tres proyectos son estrictamente descriptivos.',
        '', '## 6. Escenarios territoriales por mineral',
        '', 'Entornos hipotéticos **de 10, 25, 50 y 100 km**, unidos por mineral para impedir doble conteo dentro de cada combinación, '
        'recortados al ámbito de las 343 comunas e intersectados con concesiones sin atributo mineral. '
        '**No son huellas de intervención ni superficies de concesiones del mineral.** '
        'Los entornos de diferentes minerales pueden solaparse; sus áreas no deben sumarse.',
        '',tab(['Radio (km)','Mineral','n','Entorno dentro de ámbito (ha)','Coincidencia concesional (ha)','% entorno coincidente'],[
          [x['radio_km'],x['mineral'],x['n_proyectos'],fmt(x['superficie_buffer_en_ambito_ha']),
           fmt(x['superficie_concesion_en_entorno_ha']),fmt(x['porcentaje_entorno_concesionado'])+' %']
          for x in sorted(scen,key=lambda x:(number(x['radio_km']),x['mineral']))]),
        '', 'El escenario de 100 km representa una exploración de escala territorial, sin justificación como radio de impacto. '
        'El porcentaje a 10 km no debe interpretarse como porcentaje de concesiones de un mineral.',
        '', '## 7. Figuras disponibles para el informe','')
    captions={'48b':'Tres estados territoriales','49c':'Detalle territorial regional',
              '59':'Balance humedales MMA','60':'IST y sensibilidad tras actualización MMA',
              '61':'Coincidencia concesional cartográfica','69':'IST puntual por fuente y componente',
              '72':'Comparación de IST por mineral','73':'Escenarios por mineral y radio'}
    for p in published_figures:
        caption=captions.get(p.name.split('_')[0],'Resultado cartográfico')+' — '+p.stem
        add('### '+p.stem,'',figure(p,caption),'')
    add('## 8. Catálogo de outputs y trazabilidad',
        '', 'Las rutas siguientes se publican con este informe mediante el procedimiento selectivo de staging indicado. '
        'Los archivos locales pesados (`data/raw`, `data/processed`, GeoPackage, checkpoints y SVG) no se publican.',
        '', '### 8.1 Reportes CSV y JSON seleccionados','')
    for p in public_reports:add('- '+link(p))
    add('', '### 8.2 Figuras PNG seleccionadas','')
    for p in published_figures:add('- '+link(p))
    add('','### 8.3 Scripts para reproducir esta etapa','')
    scripts=[p for p in sorted((ROOT/'src').glob('*.py')) if re.match(r'^(6[5-9]|7[0-4])[a-z]?_',p.name)]
    for p in scripts:add('- '+link(p))
    add('','## 9. Controles de calidad y estado de validación',
        '', '- IST puntual: 347/347 unidades; 292 OA y 55 proyectos; nueve aportes verificables por registro.',
        '- Regionalización: 347/347 asignadas; una excepción costera documentada para OA 162.',
        '- Coincidencia poligonal: 144/144 combinaciones calculadas, recorte por región y ámbito.',
        '- Humedales MMA: coincidencia nacional contrastada con paso 58.',
        '- Puntos sensibles: 2.903 comunidades indígenas y 4.637 atractivos turísticos, con indicadores de registros separados de los de superficie.',
        '- Clasificación mineral: 55/55 etiquetas auditadas contra inventario histórico.',
        '- Entornos: 24/24 escenarios completos, con uniones por mineral y recorte territorial.',
        '', '## 10. Limitaciones de interpretación',
        '', '1. Un derecho concesional no equivale a ejecución minera ni implica una presión ambiental efectiva.',
        '2. Los porcentajes de registros puntuales no son equivalentes a los porcentajes de superficie.',
        '3. Las concesiones no identifican mineral: su coincidencia con entornos etiquetados no habilita atribución mineral.',
        '4. Los entornos circulares son supuestos geométricos exploratorios; no representan impacto, proyecto ni construcción futura.',
        '5. Las 292 huellas OA son candidatas y pueden contener infraestructuras auxiliares o no operativas.',
        '6. La cobertura y vigencia temática de las otras ocho componentes sensibles no se ha auditado exhaustivamente.',
        '7. Las distancias sin candidato a menos de 200 km no proporcionan una distancia mínima exacta.',
        '8. El análisis por mineral utiliza tamaños muestrales desiguales. No se realizan pruebas inferenciales.',
        '', '## 11. Pendientes para el artículo',
        '', '- Seleccionar y justificar una escala exploratoria principal de buffers, si se desea incluirla.',
        '- Revisar visualmente las figuras 69, 72 y 73 antes de elegir las imágenes del manuscrito.',
        '- Completar la verificación temática del universo OA y la validación de proyectos con geometrías de fuente primaria cuando existan.',
        '- Si se necesitan coincidencias entre **buffers** y capas sensibles, ejecutar ese cruce aparte; no está contenido en el paso 73.',
        '', '---','', '*Generado automáticamente por `src/74_actualizar_informe_integral_enmc.py` a partir de outputs disponibles en el repositorio de trabajo.*','')
    dest=D/'INFORME_INTEGRAL_ENMC.md'
    dest.write_text('\n'.join(lines),encoding='utf-8')
    # Relative manifest created for selective staging, not list of private data.
    manifest=[dest.relative_to(ROOT).as_posix(),Path('src/74_actualizar_informe_integral_enmc.py').as_posix()]
    manifest+= [p.relative_to(ROOT).as_posix() for p in public_reports+published_figures+scripts]
    extra=[D/'72_resultados_por_mineral_ENMC.md',R/'70_overlap_regional_componentes.csv',
           R/'71_puntos_sensibles_coincidencia_regional.csv']
    manifest+=[p.relative_to(ROOT).as_posix() for p in extra if p.exists()]
    manifest=list(dict.fromkeys(manifest))
    (D/'74_archivos_para_git.txt').write_text('\n'.join(manifest)+'\n',encoding='utf-8')
    print('=== PASO 74 ===')
    print('VALIDADO: 347 IST, 144 overlaps, 55 proyectos, 24 escenarios')
    print('INFORME:',dest)
    print('MANIFIESTO:',D/'74_archivos_para_git.txt')
    print('ARCHIVOS:',len(manifest))
    print('NO se hizo git add, commit, push ni envío de correo')

if __name__=='__main__': main()
