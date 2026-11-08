#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 61. Mapas regionales actualizados de coincidencia areal concesional (provisional).

Se representan por separado tres componentes: humedales, areas de desarrollo
indigena y sitios prioritarios + reservas de biosfera (union conceptual).
Los mapas son descriptivos, NO calculan nuevos porcentajes nacionales, NO
atribuyen mineral a las concesiones y NO representan impacto efectivo.

Uso:
  python -u src/61_mapas_coincidencia_humedales_mma.py
  python -u src/61_mapas_coincidencia_humedales_mma.py --zona centro

Salidas en outputs/figures/enmc/: 61_overlap_mma_{zona}.{png,svg}
Reporte de control: reports/enmc/61_control_overlap_cartografico_mma.csv
"""
from __future__ import annotations
import argparse
from pathlib import Path
import unicodedata
import warnings
import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import pandas as pd
import shapely
from shapely.errors import GEOSException
from shapely.geometry import GeometryCollection

CRS = 'EPSG:6933'
ZONAS = {
 'norte': ('NORTE GRANDE Y NORTE CHICO', 'Arica y Parinacota · Tarapacá · Antofagasta · Atacama · Coquimbo',
           ('arica y parinacota','tarapaca','antofagasta','atacama','coquimbo')),
 'centro': ('ZONA CENTRAL', 'Valparaíso · Metropolitana · O’Higgins',
            ('valparaiso','metropolitana','ohiggins')),
}
COMPONENTES = {
 'humedales': ('HUMEDALES MMA', ('humedales_mma_nacional',)),
 'desarrollo_indigena': ('ÁREAS DE DESARROLLO INDÍGENA', ('areas_desarrollo_indigena',)),
 'sitios_reservas': ('SITIOS PRIORITARIOS Y RESERVAS', ('sitios_prioritarios','reservas_biosfera')),
}
INK='#223645'; MUTED='#5c6e7b'; OUTLINE='#9baab5'; BG='#e5eaf0'
SENS_COLOR='#d3c4a5'; CON_COLOR='#285f86'; RES_COLOR='#cc6d32'


def norm(s):
    t=unicodedata.normalize('NFKD',str(s).lower())
    return ''.join(c for c in t if not unicodedata.combining(c) and c.isalnum())


def leer(path):
    if not path.exists():
        raise FileNotFoundError(path)
    d=gpd.read_file(path,engine='pyogrio')
    if d.crs is None: raise ValueError(f'CRS ausente: {path}')
    return d.to_crs(CRS)


def poligono(geom):
    if geom is None or geom.is_empty: return GeometryCollection()
    if not geom.is_valid: geom=shapely.make_valid(geom)
    if geom.geom_type in ('Polygon','MultiPolygon'): return geom
    parts=[]
    for p in shapely.get_parts(geom):
        if p.geom_type in ('Polygon','MultiPolygon') and not p.is_empty: parts.append(p)
    return shapely.union_all(parts) if parts else GeometryCollection()


def region_mask(regiones, zone):
    tokens=[norm(i) for i in ZONAS[zone][2]]
    values=regiones.nomreg.map(norm)
    rows=[]
    for t in tokens:
        choices=regiones.index[values.str.contains(t,regex=False)].tolist()
        if len(choices)!=1: raise ValueError(f'No se identificó región {t}: {choices}')
        rows.append(choices[0])
    selected=regiones.loc[rows].copy()
    return selected,poligono(shapely.union_all([poligono(g) for g in selected.geometry]))


def clip_parts(source,mask,label):
    b=mask.bounds
    subset=source.cx[b[0]:b[2],b[1]:b[3]]
    parts=[]; fixes=0
    for geom in subset.geometry:
        if geom is None or geom.is_empty: continue
        if not geom.is_valid: fixes+=1
        g=poligono(geom)
        if g.is_empty or not g.intersects(mask): continue
        try: piece=poligono(g.intersection(mask))
        except GEOSException:
            piece=poligono(shapely.make_valid(g).intersection(mask)); fixes+=1
        if not piece.is_empty: parts.append(piece)
    print(f'  {label}: candidatos={len(subset)}, recortados={len(parts)}, reparaciones={fixes}',flush=True)
    return parts


def to_frame(geom):
    if geom is None or geom.is_empty: return None
    return gpd.GeoSeries([geom],crs=CRS)


def plot_geom(ax, geom, color, z=3, alpha=1, linewidth=0):
    s=to_frame(geom)
    if s is not None:
        s.plot(ax=ax,color=color,edgecolor=color,linewidth=linewidth,alpha=alpha,zorder=z,rasterized=True)


def report_national(root):
    """Check source CSV only; avoid recalculating nationwide geometry."""
    files={
      'humedales':root/'reports/enmc/58_overlap_humedales_mma_resumen.csv',
      'desarrollo_indigena':root/'reports/enmc/40_overlap_areas_desarrollo_indigena.csv',
      'sitios_reservas':root/'reports/enmc/42_overlap_biodiversidad_conjunta.csv',
    }
    for key,p in files.items():
        d=pd.read_csv(p,encoding='utf-8-sig')
        if len(d)!=1: raise ValueError(f'Esperaba una fila: {p}')
        v=float(d.iloc[0]['porcentaje_sensible_concesionada'])
        print(f'  Indicador de referencia (ver fuente) ({key}): {v:.4f} %',flush=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    ap.add_argument('--zona',choices=['norte','centro','ambas'],default='ambas')
    ap.add_argument('--dpi',type=int,default=240)
    ap.add_argument('--simplificacion-metros',type=float,default=80.,help='Solo para dibujar, no para intersecciones')
    args=ap.parse_args()
    root=args.root.resolve(); base=root/'data/processed/enmc'
    print('=== PASO 61: CARTOGRAFIA DE COINCIDENCIAS CONCESIONALES (HUMEDALES MMA) ===',flush=True)
    report_national(root)
    regiones=leer(root/'data/processed/regiones_consolidadas.gpkg')
    if len(regiones)!=16 or 'nomreg' not in regiones.columns:
        raise ValueError('Se requieren 16 regiones y campo nomreg')
    C=leer(base/'35_concesiones_constituidas_ambito.gpkg')
    L=leer(base/'35_concesion_residual_ambito.gpkg')
    if len(C)!=1 or len(L)!=1: raise ValueError('Se esperaban las uniones concesionales en 1 geometría')
    geom_C=poligono(C.geometry.iloc[0]);geom_L=poligono(L.geometry.iloc[0])
    sens={}
    for _, (_, keys) in COMPONENTES.items():
        for k in keys:
            p = (base/'sensibilidad'/'56_humedales_mma_nacional.gpkg'
                 if k == 'humedales_mma_nacional'
                 else base/'sensibilidad'/f'39_{k}.gpkg')
            sens[k] = leer(p)
    output=root/'outputs/figures/enmc';output.mkdir(parents=True,exist_ok=True)
    report=root/'reports/enmc';report.mkdir(parents=True,exist_ok=True)
    results=[]
    for zone in (['norte','centro'] if args.zona=='ambas' else [args.zona]):
        print(f'-- {zone.upper()} --',flush=True)
        r,mask=region_mask(regiones,zone)
        c_zone=poligono(geom_C.intersection(mask));l_zone=poligono(geom_L.intersection(mask))
        fig=plt.figure(figsize=(17,9.8),facecolor='white')
        fig.text(.06,.956,'COINCIDENCIA TERRITORIAL CON CONCESIONES MINERAS',size=18,weight='bold',color=INK)
        fig.text(.06,.924,f'{ZONAS[zone][0]} · {ZONAS[zone][1]}',size=10.2,color=MUTED)
        fig.add_artist(Line2D([.06,.94],[.898,.898],transform=fig.transFigure,color='#d8e1e6',lw=1))
        for j,(comp,(title,names)) in enumerate(COMPONENTES.items()):
            x=.06+j*.306
            fig.text(x,.863,f'{j+1:02d}   {title}',size=10.4,weight='bold',color=INK)
            ax=fig.add_axes([x,.213,.275,.606]);ax.set_facecolor('white')
            pieces=[]
            for name in names:pieces.extend(clip_parts(sens[name],mask,f'{zone}/{name}'))
            # One union per component, so overlaps inside the same component are not double-counted
            s=poligono(shapely.union_all(pieces)) if pieces else GeometryCollection()
            covered=poligono(s.intersection(c_zone)) if not s.is_empty else GeometryCollection()
            latent=poligono(s.intersection(l_zone)) if not s.is_empty else GeometryCollection()
            # Conservation: residual is contained in conceded up to numerical tolerance
            if latent.area > covered.area + 100: raise RuntimeError(f'Inconsistent residual for {comp}')
            # Disjoint categories: outside concession; residual; conceded OA.
            oa_concedida = poligono(covered.difference(latent))
            libre = poligono(s.difference(covered))
            mismatch = abs(s.area - (libre.area + oa_concedida.area + latent.area))
            if mismatch > max(1., s.area * 1e-8):
                raise RuntimeError(f'Balance territorial inconsistente {zone}/{comp}: {mismatch} m2')
            # Simplification is only for rendering; metrics are based on exact geometries.
            def render(g,color,z):
                if g.is_empty:return
                if args.simplificacion_metros>0:
                    g=poligono(g.simplify(args.simplificacion_metros,preserve_topology=True))
                plot_geom(ax,g,color,z)
            render(libre,SENS_COLOR,2)
            render(latent,RES_COLOR,3)
            render(oa_concedida,CON_COLOR,4)
            r.boundary.plot(ax=ax,color=OUTLINE,linewidth=.6,zorder=7)
            xmin,ymin,xmax,ymax=mask.bounds; dx=(xmax-xmin)*.035;dy=(ymax-ymin)*.035
            ax.set_xlim(xmin-dx,xmax+dx);ax.set_ylim(ymin-dy,ymax+dy)
            ax.set_aspect('equal');ax.axis('off')
            s_ha=s.area/1e4;cov_ha=covered.area/1e4;res_ha=latent.area/1e4
            pct=cov_ha/s_ha*100 if s_ha else float('nan')
            label = (f'{pct:.2f}% de cobertura coincidente con concesión'
                     if s_ha > 0 else 'Sin cobertura registrada en esta zona')
            fig.text(x+.137,.171,label,size=8.2,ha='center',color=INK)
            print(f'  {comp}: sensible={s_ha:,.2f} ha, concesionada={cov_ha:,.2f} ha ({pct:.2f}%), residual={res_ha:,.2f} ha',flush=True)
            results.append({'zona':zone,'componente':comp,'sensible_ha':s_ha,'concesionada_ha':cov_ha,'residual_ha':res_ha,'coincidente_oa_ha':oa_concedida.area/1e4,
                            'no_concesionada_ha':libre.area/1e4,'error_balance_m2':mismatch,
                            'porcentaje_concesionada':pct,'observacion':'Indicador regional de intersección, no reemplaza porcentaje nacional; residual provisional'})
        fig.legend(handles=[Patch(facecolor=SENS_COLOR,label='Sin concesión constituida'),Patch(facecolor=RES_COLOR,label='Residual provisional'),Patch(facecolor=CON_COLOR,label='Concesión coincidente con OA')],loc='center',bbox_to_anchor=(.5,.121),ncol=3,frameon=False,fontsize=9)
        fig.add_artist(Line2D([.06,.94],[.092,.092],transform=fig.transFigure,color='#d8e1e6',lw=1))
        fig.text(.06,.077,'Fuentes: humedales MMA/SIMBIO; otras capas normalizadas; concesiones SERNAGEOMIN. EPSG:6933.',size=8.3,color=MUTED)
        fig.text(.06,.057,'Las coincidencias espaciales NO prueban impactos, actividad vigente ni derechos sobre un mineral específico.',size=8.3,color=INK)
        fig.text(.06,.037,'Residual provisional = concesión constituida menos huella OA seleccionada; sin validar estado operativo ni nuevas huellas COCHILCO.',size=8.1,color=MUTED)
        for fmt in ('png','svg'):
            p=output/f'61_overlap_mma_{zone}.{fmt}'
            fig.savefig(p,facecolor='white',dpi=args.dpi if fmt=='png' else None)
            print(f'  {fmt.upper()}: {p}',flush=True)
        plt.close(fig)
    dest=report/'61_control_overlap_cartografico_mma.csv';pd.DataFrame(results).to_csv(dest,index=False,encoding='utf-8-sig')
    print('CONTROL:',dest,flush=True)
    print('PASO 61 FINALIZADO',flush=True)

if __name__=='__main__':main()
