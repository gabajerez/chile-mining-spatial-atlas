#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 59 | Auditoria de balance y figura de coincidencia de humedales MMA.

No descarga ni modifica geometrias; lee salidas verificables del paso 58.
Ejecutar desde cualquier directorio: python src/59_validar_y_visualizar_overlap_humedales.py
"""
from __future__ import annotations
import json
import math
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports' / 'enmc'
FIG = ROOT / 'outputs' / 'figures' / 'enmc'
R = REPORT / '58_overlap_humedales_mma_resumen.csv'
T = REPORT / '58_overlap_humedales_mma_teselas.csv'
J = REPORT / '58_overlap_humedales_mma_control.json'
COLUMNS = {
 'superficie_humedales_unica_ha':'superficie_sensible_unica_ha',
 'superficie_humedales_concesionada_ha':'superficie_sensible_concesionada_ha',
 'superficie_humedales_residual_ha':'superficie_sensible_residual_provisional_ha',
 'superficie_humedales_concesionada_coincide_oa_ha':'superficie_sensible_concesionada_coincidente_oa_ha',
}

def assert_close(a, b, name, abs_tol=1e-4):
    if not math.isclose(float(a), float(b), rel_tol=1e-10, abs_tol=abs_tol):
        raise AssertionError(f'{name}: {a} versus {b}')

def main():
    FIG.mkdir(parents=True, exist_ok=True)
    REPORT.mkdir(parents=True, exist_ok=True)
    for f in (R,T,J):
        if not f.is_file():
            raise FileNotFoundError(f)
    r = pd.read_csv(R)
    t = pd.read_csv(T)
    j = json.loads(J.read_text(encoding='utf-8-sig'))
    if len(r) != 1:
        raise AssertionError(f'Resumen tiene {len(r)} filas, se espera 1')
    if 'tesela' not in t or t.tesela.duplicated().any():
        raise AssertionError('Teselas duplicadas o sin identificador')
    if len(t) != int(r.loc[0,'n_teselas']):
        raise AssertionError('Diferencia en cantidad de teselas')
    if t[list(COLUMNS)].isna().any().any() or (t[list(COLUMNS)] < -1e-8).any().any():
        raise AssertionError('Valores ausentes o superficies negativas')
    for tile_col, total_col in COLUMNS.items():
        v = float(t[tile_col].sum())
        assert_close(v, r.loc[0,total_col], tile_col)
        assert_close(v, j['control'][total_col], tile_col + '/JSON')
    h = float(r.loc[0,'superficie_sensible_unica_ha'])
    c = float(r.loc[0,'superficie_sensible_concesionada_ha'])
    resid = float(r.loc[0,'superficie_sensible_residual_provisional_ha'])
    oa = float(r.loc[0,'superficie_sensible_concesionada_coincidente_oa_ha'])
    non_c = h - c
    if h <= 0 or min(non_c,resid,oa) < -1e-6:
        raise AssertionError('Balance con superficies incompatibles')
    assert_close(c, resid+oa, 'concesion = residual + OA')
    assert_close(h, non_c+resid+oa, 'humedales = 3 clases')
    if (t['superficie_humedales_residual_ha'] > t['superficie_humedales_concesionada_ha']+1e-7).any():
        raise AssertionError('Residual supera concesion en al menos una tesela')
    if (t['superficie_humedales_concesionada_ha'] > t['superficie_humedales_unica_ha']+1e-7).any():
        raise AssertionError('Concesion supera humedales en al menos una tesela')
    per = [100*non_c/h, 100*resid/h, 100*oa/h]
    assert_close(sum(per),100,'porcentajes suman 100')
    assert_close(100*c/h,r.loc[0,'porcentaje_sensible_concesionada'],'porcentaje concesionado',1e-8)
    assert_close(100*resid/h,r.loc[0,'porcentaje_sensible_residual_provisional'],'porcentaje residual',1e-8)

    print('=== PASO 59: AUDITORIA Y FIGURA HUMEDALES MMA ===')
    print(f'Teselas verificadas: {len(t)} | Superficie H: {h:,.3f} ha')
    print(f'Coincide concesion: {c:,.3f} ha ({100*c/h:.4f}%)')
    print(f'Residual provisional: {resid:,.3f} ha ({100*resid/h:.4f}%)')
    print(f'Coincidente OA: {oa:,.3f} ha ({100*oa/h:.4f}%)')
    print('Balance cerrado: H = no concesionado + residual + coincidente OA')

    labels = ['Sin coincidencia concesional', 'Residual concesional provisional',
              'Concesionada coincidente con huella OA']
    colors = ['#d9e5df','#377e88','#d88c50']
    fig, ax = plt.subplots(figsize=(12.5,3.5))
    fig.subplots_adjust(left=.045,right=.98,top=.79,bottom=.27)
    offset = 0
    for p,color in zip(per,colors):
        ax.barh([0], [p], left=[offset], height=.40, color=color, edgecolor='white',linewidth=1)
        if p >= 4:
            ax.text(offset+p/2,0,f'{p:.2f} %'.replace('.',','),ha='center',va='center',
                    fontsize=12,fontweight='bold',color='#172e35')
        offset += p
    ax.set_xlim(0,100)
    ax.set_ylim(-.55,.55)
    ax.set_yticks([])
    ax.set_xlabel('Porcentaje de la superficie inventariada de humedales en el ambito de estudio', fontsize=10)
    ax.set_xticks([0,20,40,60,80,100],labels=['0','20','40','60','80','100 %'])
    ax.spines[['left','right','top']].set_visible(False)
    ax.grid(axis='x',alpha=.15)
    ax.set_axisbelow(True)
    fig.suptitle('Humedales MMA y concesiones mineras constituidas', fontsize=15,fontweight='bold',y=.96)
    fig.legend(handles=[Patch(facecolor=k,label=lab) for k,lab in zip(colors,labels)],
               loc='lower center',bbox_to_anchor=(.5,.01),ncol=3,frameon=False,fontsize=9)
    fig.text(.96,.79,f'Superficie total: {h:,.0f} ha'.replace(',','.'),ha='right',fontsize=9,color='#46525a')
    png=FIG/'59_balance_humedales_mma_concesiones.png'
    svg=FIG/'59_balance_humedales_mma_concesiones.svg'
    fig.savefig(png,dpi=240,facecolor='white')
    fig.savefig(svg,facecolor='white')
    plt.close(fig)

    audit={
      'paso':59,'utc':datetime.now(timezone.utc).isoformat(),
      'fuentes':['reports/enmc/58_overlap_humedales_mma_resumen.csv',
                 'reports/enmc/58_overlap_humedales_mma_teselas.csv',
                 'reports/enmc/58_overlap_humedales_mma_control.json'],
      'n_teselas':len(t),'balance_ha':{
      'humedales_total':h,'sin_coincidencia_concesional':non_c,
      'residual_provisional':resid,'concesion_coincidente_oa':oa,
      'concesion_total':c},
      'porcentaje_ha':{'sin_concesion':per[0],'residual_provisional':per[1],
                       'coincidente_oa':per[2],'concesion_total':100*c/h},
      'checks':{'teselas_sin_duplicados':True,'sumas_csv_json':True,
                'balance_excluyente':True,'restricciones_por_tesela':True},
      'cautela':'Coincidencia espacial de humedales con derechos mineros constituidos, NO prueba de actividad, impacto o mineral. Residual provisional depende de seleccion OA y aun no descuenta nuevos poligonos COCHILCO. Fuente MMA y area comunal difieren del paso 40.',
      'figuras':[str(png.relative_to(ROOT)),str(svg.relative_to(ROOT))]
    }
    p=REPORT/'59_control_balance_humedales_mma.json'
    p.write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    method=ROOT/'docs'/'metodologia'
    method.mkdir(parents=True,exist_ok=True)
    md=method/'59_resultados_humedales_mma.md'
    md.write_text(f'''# Coincidencia de humedales MMA y concesiones mineras (pasos 54-59)\n\n## Universo y procedencia\n- Servicio: Inventario Nacional de Humedales MMA (SIMBIO, FeatureServer/0); descarga documentada en el paso 54.\n- Registros anunciados: 117.983; geometrías utilizables: 117.969; sin geometría: 14 (registrados, no reemplazados).\n- Proyección de área: EPSG:6933.\n- Ámbito de análisis: 343 comunas, superficie de estudio 75.256.754,28 ha.\n- Coincidencia con concesiones constituidas y residual: archivos preparados en paso 35.\n- Cálculo por 110 teselas disjuntas, intersección exacta y superficie única tras unión dentro de cada tesela (paso 58).\n\n## Resultados dentro del ámbito de estudio\n- Superficie única de humedales: **{h:,.2f} ha**.\n- Coincidencia con concesiones constituidas: **{c:,.2f} ha ({100*c/h:.4f} %)**.\n- Residual concesional provisional: **{resid:,.2f} ha ({100*resid/h:.4f} %)**.\n- Coincidencia de concesión con huella OA seleccionada: **{oa:,.2f} ha ({100*oa/h:.4f} %)**.\n- Sin coincidencia concesional: **{non_c:,.2f} ha ({100*non_c/h:.4f} %)**.\n- Balance: concesión constituida = residual provisional + coincidencia con huella OA (dentro de la superficie de humedales), con error numérico despreciable.\n\n## Alcance y limitaciones\nLos resultados miden **superposición espacial** con derechos mineros constituidos. No demuestran intervención, explotación, daño ambiental ni asociación de las concesiones a minerales críticos. La categoría residual es provisional porque depende de la selección de unidades OA y aún no descuenta nuevas huellas de proyectos COCHILCO verificadas. La cifra previa de 35,66 % se calculó sobre una fuente distinta, restringida a tres regiones, y no es directamente comparable. La distribución nacional de humedales afecta el denominador. Validar metadatos temáticos y temporales de la fuente MMA antes de publicación.\n\n## Reproducibilidad\nEjecutar `python src/59_validar_y_visualizar_overlap_humedales.py` tras el paso 58. Entradas: `reports/enmc/58_overlap_humedales_mma_resumen.csv`, `58_overlap_humedales_mma_teselas.csv` y `58_overlap_humedales_mma_control.json`. Salidas: `reports/enmc/59_control_balance_humedales_mma.json`, `outputs/figures/enmc/59_balance_humedales_mma_concesiones.png` y `.svg`. Datos geoespaciales grandes se gestionan separadamente de Git; preservar rutas, fuentes y metadatos.\n''',encoding='utf-8')
    print(f'JSON: {p}')
    print(f'Figura: {png}')
    print(f'Documentacion: {md}')
    print('PASO 59 FINALIZADO')

if __name__=='__main__':
    main()
