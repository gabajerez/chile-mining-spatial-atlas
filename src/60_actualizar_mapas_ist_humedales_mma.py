#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 60: mapas actualizados con humedales MMA nacionales, regionales de sensibilidad territorial e IST para ENMC.

Genera dos mapas de DOS paneles (OA y COCHILCO) con una misma escala IST,
sobre cuatro componentes ambientales como contexto cartografico. No modifica
capas, no calcula IST nuevo y NO interpreta coincidencias como impactos.

Requisitos: geopandas, pandas, shapely >=2, matplotlib, pyogrio.
Uso:
 python -u src/60_actualizar_mapas_ist_humedales_mma.py
 python -u src/60_actualizar_mapas_ist_humedales_mma.py --zona centro

Salidas:
 outputs/figures/enmc/60_ist_humedales_mma_norte.{png,svg}
 outputs/figures/enmc/60_ist_humedales_mma_centro.{png,svg}
 reports/enmc/60_control_cartografia_ist_mma.csv
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
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import GeometryCollection
from shapely.errors import GEOSException

CRS = 'EPSG:6933'  # para mostrar geometria; distancias IST ya calculadas en paso 43
ZONAS = {
    'norte': {
        'titulo': 'NORTE GRANDE Y NORTE CHICO',
        'regiones': 'Arica y Parinacota · Tarapacá · Antofagasta · Atacama · Coquimbo',
        'tokens': ('arica y parinacota', 'tarapaca', 'antofagasta', 'atacama', 'coquimbo'),
    },
    'centro': {
        'titulo': 'ZONA CENTRAL',
        'regiones': 'Valparaíso · Metropolitana · Libertador General Bernardo O’Higgins',
        'tokens': ('valparaiso', 'metropolitana', 'ohiggins'),
    },
}
# Lineas y rellenos suaves para evitar ocultar los registros mineros
TEMAS = {
    'areas_protegidas': dict(titulo='Áreas protegidas', color='#7ea68d', alpha=.27, lw=.18),
    'sitios_prioritarios': dict(titulo='Sitios prioritarios', color='#d5ae62', alpha=.24, lw=.18),
    'glaciares': dict(titulo='Glaciares', color='#82bdd2', alpha=.70, lw=.08),
    'humedales': dict(titulo='Humedales MMA', color='#9670ab', alpha=.72, lw=.12),
}
TINTA = '#1f3340'
MUTED = '#60727e'
LINE = '#dce4e8'


def normalizar(v):
    s = unicodedata.normalize('NFKD', str(v).lower())
    return ''.join(c for c in s if not unicodedata.combining(c) and c.isalnum())


def leer(path):
    if not path.exists():
        raise FileNotFoundError(f'Insumo faltante: {path}')
    frame = gpd.read_file(path, engine='pyogrio')
    if frame.crs is None:
        raise ValueError(f'Sin CRS: {path}')
    frame = frame.loc[frame.geometry.notna() & ~frame.geometry.is_empty].copy()
    return frame.to_crs(CRS)


def solo_poligonos(geom):
    if geom is None or geom.is_empty:
        return GeometryCollection()
    if geom.geom_type in ('Polygon', 'MultiPolygon'):
        return geom
    if geom.geom_type == 'GeometryCollection':
        valid = [solo_poligonos(x) for x in geom.geoms]
        valid = [x for x in valid if not x.is_empty]
        return shapely.union_all(valid) if valid else GeometryCollection()
    return GeometryCollection()


def reparar(geom):
    if geom is None or geom.is_empty:
        return GeometryCollection()
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
    return solo_poligonos(geom)


def regionalizar(regiones, zona):
    tokens = [normalizar(v) for v in ZONAS[zona]['tokens']]
    nombres = regiones['nomreg'].map(normalizar)
    indices = []
    for term in tokens:
        matches = regiones.index[nombres.str.contains(term, regex=False)].tolist()
        if len(matches) != 1:
            raise ValueError(f"Región ambigua para {term}: {regiones.loc[matches, 'nomreg'].tolist()}")
        indices.append(matches[0])
    subset = regiones.loc[indices].copy()
    mask = solo_poligonos(shapely.union_all([reparar(g) for g in subset.geometry]))
    if mask.is_empty or not mask.is_valid:
        raise ValueError(f'Máscara regional inválida: {zona}')
    return subset, mask


def filtrar_y_recortar(gdf, mascara, etiqueta):
    """Recorte individual y reparaciones EN MEMORIA, sin alterar insumos."""
    bounds = mascara.bounds
    subset = gdf.cx[bounds[0]:bounds[2], bounds[1]:bounds[3]].copy()
    if subset.empty:
        return subset
    coords, ids = [], []
    n_reparadas = 0
    for idx, geom in subset.geometry.items():
        if geom is None or geom.is_empty:
            continue
        if geom.geom_type in ('Point', 'MultiPoint'):
            if mascara.covers(geom):
                ids.append(idx); coords.append(geom)
            continue
        if not geom.is_valid:
            n_reparadas += 1
            geom = reparar(geom)
        try:
            if not geom.intersects(mascara):
                continue
            piece = solo_poligonos(geom.intersection(mascara))
        except GEOSException:
            geom = reparar(geom)
            piece = solo_poligonos(geom.intersection(mascara))
            n_reparadas += 1
        if not piece.is_empty:
            ids.append(idx); coords.append(piece)
    out = subset.loc[ids].copy()
    out.geometry = gpd.GeoSeries(coords, index=out.index, crs=CRS)
    print(f'  {etiqueta}: entrada={len(subset)}, visibles={len(out)}, reparadas={n_reparadas}', flush=True)
    return out


def dibujar_poligonos(ax, frame, style, tol):
    if frame.empty:
        return
    work = frame[['geometry']].copy()
    work.geometry = work.geometry.map(reparar)
    work = work.loc[~work.geometry.is_empty].copy()
    if work.empty:
        return
    if tol > 0:
        work.geometry = work.geometry.simplify(tol, preserve_topology=True)
        work = work.loc[~work.geometry.is_empty].copy()
    if not work.empty:
        work.plot(ax=ax, facecolor=style['color'], edgecolor=style['color'],
                  alpha=style['alpha'], linewidth=style['lw'], zorder=3,
                  rasterized=True)


def asociar_ist(oa, proyectos, csv_path):
    df = pd.read_csv(csv_path, dtype={'id_fuente': str}, encoding='utf-8-sig')
    needed = {'fuente','id_fuente','nombre','IST_100'}
    if not needed.issubset(df.columns):
        raise ValueError(f'CSV IST sin columnas: {sorted(needed-set(df.columns))}')
    if len(df) != 347 or set(df.fuente) != {'OA_ENMC','COCHILCO_ENMC'}:
        raise ValueError(f'Se esperaban 347 filas IST (292 OA, 55 COCHILCO); hay {len(df)}')
    if df.duplicated(['fuente','id_fuente']).any():
        raise ValueError('Claves duplicadas fuente/id_fuente en IST')
    if df.IST_100.isna().any() or not df.IST_100.between(0,100).all():
        raise ValueError('IST contiene nulos o valores fuera de 0..100')

    # OA usa OBJECTID; evitar asimilar erroneamente ID_OA, que no es unico.
    oa = oa.loc[oa['estado_oa_provisional'].eq('CANDIDATA_OPERACION_POR_TIPO')].copy()
    if len(oa) != 292 or 'OBJECTID' not in oa.columns:
        raise ValueError('Se esperaban 292 OA candidatas con OBJECTID')
    oa['id_fuente'] = oa.OBJECTID.astype(str).str.replace(r'\.0$', '', regex=True)
    # Preservar el indicador preexistente para evitar sufijos _x/_y al unir.
    if 'IST_100' in oa.columns:
        oa = oa.rename(columns={'IST_100': 'IST_100_ORIGINAL_OA'})
    ist_oa = df[df.fuente == 'OA_ENMC'][['id_fuente','nombre','IST_100']].rename(columns={'nombre':'nombre_ist'})
    oa = oa.merge(ist_oa, on='id_fuente', how='left', validate='one_to_one')
    if oa['IST_100'].isna().any():
        raise ValueError('No se emparejaron todas las OA por OBJECTID')
    if 'IST_100_ORIGINAL_OA' in oa.columns:
        orig = pd.to_numeric(oa['IST_100_ORIGINAL_OA'], errors='coerce')
        valid = orig.notna()
        if valid.any():
            error = (orig[valid] - oa.loc[valid, 'IST_100']).abs()
            print(f'  Contraste IST OA: {int(valid.sum())} comparables, error maximo={error.max():.8f}', flush=True)
            # El IST OA original corresponde a la versión previa de humedales.
            # La discrepancia es esperada; se controla después contra paso 43.
            if (error > 12.00001).any():
                raise ValueError('Diferencia IST OA fuera de tolerancia del peso HU (12 puntos)')

    # Paso 43: COCHILCO carece de ID estable; enumeracion 1..55 en orden de lectura.
    # Se verifica NOMBRE para evitar asociaciones por simple posicion sin control.
    if len(proyectos) != 55:
        raise ValueError(f'COCHILCO requiere 55 filas, hay {len(proyectos)}')
    if not proyectos.geom_type.isin(['Point','MultiPoint']).all():
        raise ValueError('COCHILCO debe tener puntos representativos')
    proyectos = proyectos.reset_index(drop=True).copy()
    proyectos['id_fuente'] = pd.Series(range(1, len(proyectos)+1)).astype(str)
    if 'IST_100' in proyectos.columns:
        proyectos = proyectos.rename(columns={'IST_100': 'IST_100_ORIGINAL_COCHILCO'})
    ist_proy = df[df.fuente == 'COCHILCO_ENMC'][['id_fuente','nombre','IST_100']].rename(columns={'nombre':'nombre_ist'})
    proyectos = proyectos.merge(ist_proy, on='id_fuente', how='left', validate='one_to_one')
    if proyectos.IST_100.isna().any():
        raise ValueError('No se emparejaron todos los proyectos COCHILCO')
    if 'proyecto' not in proyectos.columns:
        raise ValueError('Falta campo proyecto en COCHILCO')
    mismatch = proyectos.loc[
        proyectos.apply(lambda x: normalizar(x['proyecto']) != normalizar(x['nombre_ist']), axis=1)
    ]
    if len(mismatch):
        raise ValueError('Correspondencia de proyectos no coincide por nombre: '
                         + str(mismatch[['id_fuente','proyecto','nombre_ist']].head(5).to_dict('records')))
    if oa['id_fuente'].duplicated().any():
        raise ValueError('OBJECTID OA duplicado')
    print('Correspondencias IST: 292/292 OA y 55/55 COCHILCO', flush=True)
    return oa, proyectos


def figura(root, zona, regiones, oa, proy, sensibilidad, dpi, simplificar):
    reg, mascara = regionalizar(regiones, zona)
    oa_sub = filtrar_y_recortar(oa, mascara, f'{zona}/OA')
    proy_sub = filtrar_y_recortar(proy, mascara, f'{zona}/COCHILCO')
    overlays = {}
    for key, frame in sensibilidad.items():
        overlays[key] = filtrar_y_recortar(frame, mascara, f'{zona}/{key}')

    fig = plt.figure(figsize=(15.4,10.9), facecolor='white')
    fig.text(.06,.958, f"SENSIBILIDAD TERRITORIAL E IST ACTUALIZADO · {ZONAS[zona]['titulo']}",
             size=18,weight='bold',color=TINTA,va='top')
    fig.text(.06,.925,ZONAS[zona]['regiones'],size=10,color=MUTED,va='top')
    fig.add_artist(Line2D([.06,.94],[.903,.903], transform=fig.transFigure, color=LINE,lw=1))
    labels=[('01','HUELLA MINERA REGISTRADA','OA · selección ENMC; condición operativa no verificada'),
            ('02','PROYECTOS DE INVERSIÓN','COCHILCO · localizaciones puntuales representativas')]
    axes=[]
    for j,(n,t,subtitle) in enumerate(labels):
        x=.062 + j*.455
        fig.text(x,.874,n,size=12,color=MUTED,weight='bold',va='top')
        fig.text(x+.043,.874,t,size=11.8,color=TINTA,weight='bold',va='top')
        fig.text(x,.843,subtitle,size=9.0,color=MUTED,va='top')
        ax=fig.add_axes([x,.238,.405,.565])
        ax.set_facecolor('white')
        for key in ('areas_protegidas','sitios_prioritarios','glaciares','humedales'):
            dibujar_poligonos(ax,overlays[key],TEMAS[key],simplificar)
        reg.plot(ax=ax,facecolor='none',edgecolor='#8e9eaa',linewidth=.7,zorder=6)
        ax.set_xlim(mascara.bounds[0]-20000,mascara.bounds[2]+20000)
        ax.set_ylim(mascara.bounds[1]-20000,mascara.bounds[3]+20000)
        ax.set_aspect('equal')
        ax.axis('off')
        axes.append(ax)

    cmap=plt.get_cmap('YlOrRd')
    norm=Normalize(vmin=0,vmax=100)
    if len(oa_sub):
        points = oa_sub.copy()
        points.geometry=points.geometry.representative_point()
        points.plot(ax=axes[0],column='IST_100',cmap=cmap,vmin=0,vmax=100,
                    markersize=34,marker='o',edgecolor='#253a46',linewidth=.36,zorder=10)
    if len(proy_sub):
        proy_sub.plot(ax=axes[1],column='IST_100',cmap=cmap,vmin=0,vmax=100,
                      markersize=65,marker='o',edgecolor='#253a46',linewidth=.50,zorder=10)

    # Franja editorial independiente: escala, leyenda y notas sin solapamientos.
    fig.text(.5,.208,'Índice de Sensibilidad Territorial (IST) · versión humedales MMA · puntos sobre 100',
             size=9.5,color=TINTA,ha='center',va='center')
    cax=fig.add_axes([.24,.178,.52,.017])
    sm=ScalarMappable(norm=norm,cmap=cmap);sm.set_array([])
    cb=fig.colorbar(sm,cax=cax,orientation='horizontal',ticks=[0,20,40,60,80,100])
    cb.ax.tick_params(labelsize=8,pad=3)
    cb.outline.set_edgecolor(LINE)
    patches=[Patch(facecolor=v['color'],edgecolor=v['color'],alpha=.7,label=v['titulo'])
             for v in TEMAS.values()]
    fig.legend(handles=patches,loc='center',bbox_to_anchor=(.5,.123),ncol=4,
               frameon=False,fontsize=8.8,columnspacing=2.2,handlelength=1.6)
    fig.add_artist(Line2D([.06,.94],[.095,.095],transform=fig.transFigure,color=LINE,lw=1))
    fig.text(.06,.080,'Fuentes: OA y COCHILCO (selección ENMC); humedales MMA nacional (117.969 polígonos). '
             'Cartografía: EPSG:6933.',size=8.2,color=MUTED,va='top')
    fig.text(.06,.062,'IST recalculado: componente humedales actualizado (peso 12 %); otros ocho componentes sin cambios. '
             'No mide impactos ni conflictos constatados.',size=8.2,color=TINTA,va='top')
    fig.text(.06,.044,'Los polígonos ambientales son contexto visual, no equivalen a áreas de impacto. OA: actividad no verificada. '
             'COCHILCO: puntos representativos, no huellas de intervención. '
             'Geometrías simplificadas solo para dibujo.',size=8.0,color=MUTED,va='top')

    dest=root/'outputs/figures/enmc'
    dest.mkdir(parents=True,exist_ok=True)
    for ext in ('png','svg'):
        path=dest/f'60_ist_humedales_mma_{zona}.{ext}'
        fig.savefig(path,facecolor='white',dpi=dpi if ext=='png' else None)
        print(f'  {ext.upper()}: {path}',flush=True)
    plt.close(fig)
    return {
        'zona':zona,'regiones':'; '.join(reg.nomreg.astype(str)),
        'oa_n':len(oa_sub),'cochilco_n':len(proy_sub),
        'ist_oa_media':oa_sub.IST_100.mean() if len(oa_sub) else np.nan,
        'ist_cochilco_media':proy_sub.IST_100.mean() if len(proy_sub) else np.nan,
        **{f'features_{name}':len(df) for name,df in overlays.items()},
        'interpretacion':'MAPA_IST_PRELIMINAR_GEOMETRIAS_OA_Y_COCHILCO_NO_VALIDADAS',
        'nota':'No usar conteos por mapa como suma nacional: poligonos pueden cruzar regiones.',
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--zona',choices=['norte','centro','ambas'],default='ambas')
    parser.add_argument('--dpi',type=int,default=250)
    parser.add_argument('--simplificar-metros',type=float,default=120.,
                        help='Solo visualización, nunca para superficies o distancias')
    args=parser.parse_args()
    root=args.root.resolve()
    print('=== PASO 60: CARTOGRAFIA IST ACTUALIZADA CON HUMEDALES MMA ===',flush=True)
    base=root/'data/processed/enmc'
    regiones=leer(root/'data/processed/regiones_consolidadas.gpkg')
    if len(regiones)!=16 or 'nomreg' not in regiones.columns:
        raise ValueError('Se esperaban 16 regiones y columna nomreg')
    oa=leer(base/'oa_enmc_candidatas.gpkg')
    proy=leer(base/'cochilco_enmc_proyectos.gpkg')
    oa,proy=asociar_ist(oa,proy,root/'reports/enmc/57_ist_enmc_humedales_mma.csv')
    sensibilidad={k:leer(base/'sensibilidad' / ('56_humedales_mma_nacional.gpkg' if k=='humedales' else f'39_{k}.gpkg')) for k in TEMAS}
    # Integridad nacional: mismos 347 IDs y diferencia explicada solo por HU.
    old=pd.read_csv(root/'reports/enmc/43_ist_enmc.csv',encoding='utf-8-sig',dtype={'id_fuente':str})
    new=pd.read_csv(root/'reports/enmc/57_ist_enmc_humedales_mma.csv',encoding='utf-8-sig',dtype={'id_fuente':str})
    keys=['fuente','id_fuente']
    if old.duplicated(keys).any() or new.duplicated(keys).any() or len(old)!=347 or len(new)!=347:
        raise ValueError('Fuentes IST inconsistentes')
    check=old[keys+['IST_100','S_HU']].merge(new[keys+['IST_100','S_HU']],on=keys,how='outer',validate='one_to_one',indicator=True,suffixes=('_43','_57'))
    if not check['_merge'].eq('both').all():
        raise ValueError('Unidades faltantes o sobrantes entre 43 y 57')
    expected=12*(check.S_HU_57-check.S_HU_43)
    error=((check.IST_100_57-check.IST_100_43)-expected).abs()
    if error.max()>1e-5:
        raise ValueError(f'Error formula diferencial IST, max={error.max()}')
    if not check.IST_100_57.between(0,100).all():
        raise ValueError('IST actualizado fuera de escala')
    print(f'Verificación diferencial 347/347: error max={error.max():.8f}; cambios={(expected.abs()>1e-5).sum()}',flush=True)
    if len(sensibilidad['humedales'])!=117969:
        raise ValueError('Inventario de humedales no contiene 117.969 polígonos')
    zonas=['norte','centro'] if args.zona=='ambas' else [args.zona]
    filas=[]
    for zona in zonas:
        print(f'-- {zona.upper()} --',flush=True)
        filas.append(figura(root,zona,regiones,oa,proy,sensibilidad,args.dpi,args.simplificar_metros))
    dest=root/'reports/enmc/60_control_cartografia_ist_mma.csv'
    dest.parent.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(filas).to_csv(dest,index=False,encoding='utf-8-sig')
    print('CONTROL:',dest,flush=True)
    print('PASO 60 FINALIZADO',flush=True)


if __name__=='__main__':
    main()
