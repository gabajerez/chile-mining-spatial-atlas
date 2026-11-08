#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 49: dos figuras regionales de detalle, tres estados ENMC (recorte exacto).

No modifica insumos ni calcula hectareas/IST. Los recortes y simplificaciones
son EXCLUSIVAMENTE cartograficos. Reutiliza las capas del paso 48b.

Salidas: outputs/figures/enmc/49c_detalle_norte_enmc.{png,svg},
         outputs/figures/enmc/49c_detalle_centro_enmc.{png,svg}
         reports/enmc/49c_control_mapas_regionales.csv
"""
from __future__ import annotations

import argparse
import unicodedata
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import pandas as pd
import shapely
from shapely.geometry import box, GeometryCollection
from shapely.errors import GEOSException

CRS = 'EPSG:6933'
COL = dict(ink='#1c2e3b', muted='#536676', outline='#8d9ba3',
           land='#f4f6f6', oa='#b45e3f', project='#176d84',
           residual='#4c85a9', discounted='#d89b55', rule='#d9e1e5')

REGION_GROUPS = {
    'norte': dict(title='NORTE GRANDE Y NORTE CHICO',
                  subtitle='Arica y Parinacota · Tarapacá · Antofagasta · Atacama · Coquimbo',
                  tokens=['arica y parinacota','tarapaca','antofagasta','atacama','coquimbo']),
    'centro': dict(title='ZONA CENTRAL',
                   subtitle='Valparaíso · Metropolitana · Libertador General Bernardo O’Higgins',
                   tokens=['valparaiso','metropolitana','ohiggins']),
}


def norm(value):
    s = unicodedata.normalize('NFKD', str(value).lower())
    return ''.join(c for c in s if not unicodedata.combining(c) and c.isalnum())


def read(path):
    if not path.exists():
        raise FileNotFoundError(f'No se encuentra el insumo: {path}')
    df = gpd.read_file(path, engine='pyogrio')
    if df.crs is None:
        raise ValueError(f'Capa sin CRS: {path}')
    return df.loc[df.geometry.notna() & ~df.geometry.is_empty].to_crs(CRS)


def region_subset(regions, group):
    if 'nomreg' not in regions:
        raise ValueError('La capa regiones_consolidadas.gpkg debe contener nomreg')
    keys = [norm(x) for x in group['tokens']]
    names = regions.nomreg.map(norm)
    # Ohiggins puede figurar como Libertador General Bernardo O'Higgins
    matching = []
    for key in keys:
        matches = regions.loc[names.str.contains(key, regex=False)]
        if len(matches) != 1:
            raise RuntimeError(f"Se esperaban 1 region para '{key}', aparecieron {len(matches)}: "
                               f"{matches.nomreg.tolist()}")
        matching.append(matches.index[0])
    return regions.loc[matching].copy()


def window(regions, fraction=0.10):
    xmin,ymin,xmax,ymax = [float(x) for x in regions.total_bounds]
    dx,dy = xmax-xmin,ymax-ymin
    padx = max(dx*fraction, 18000.)
    pady = max(dy*.055, 18000.)
    return (xmin-padx, ymin-pady, xmax+padx, ymax+pady)


def _polygon_only(geom):
    """Extrae los componentes poligonales de una geometría reparada.

    La reparación puede generar GeometryCollections con líneas o puntos;
    esos componentes no deben transformarse en supuestas superficies.
    """
    if geom is None or geom.is_empty:
        return GeometryCollection()
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom
    if geom.geom_type == "GeometryCollection":
        pieces = [_polygon_only(part) for part in geom.geoms]
        pieces = [g for g in pieces if not g.is_empty]
        return shapely.union_all(pieces) if pieces else GeometryCollection()
    return GeometryCollection()


def _repair(geom, name, position):
    if geom is None or geom.is_empty:
        return geom, False
    if geom.is_valid:
        return geom, False
    try:
        fixed = shapely.make_valid(geom)
        fixed = _polygon_only(fixed)
        if fixed.is_empty or not fixed.is_valid:
            raise ValueError("reparación sin geometría poligonal válida")
        return fixed, True
    except Exception as exc:
        raise RuntimeError(
            f"No se pudo reparar {name}, posición {position}: {exc}"
        ) from exc


def clip_to_regions(gdf, region_mask, bounds, name):
    """Recorta al territorio real de las regiones, NO a su ventana rectangular.

    Se repara en memoria cada polígono y se preservan solo áreas. Los puntos
    se incluyen únicamente cuando están dentro o sobre la frontera regional.
    """
    candidate = gdf.cx[bounds[0]:bounds[2], bounds[1]:bounds[3]].copy()
    if candidate.empty:
        print(f"  {name}: sin elementos candidatos", flush=True)
        return candidate
    is_points = candidate.geom_type.isin(['Point','MultiPoint']).all()
    keep, geometries = [], []
    repaired = 0
    for pos, (idx, geom) in enumerate(candidate.geometry.items()):
        if geom is None or geom.is_empty:
            continue
        if not is_points:
            geom, was_repaired = _repair(geom, name, pos)
            repaired += int(was_repaired)
        try:
            if not region_mask.intersects(geom):
                continue
            clipped = geom.intersection(region_mask)
        except GEOSException:
            if is_points:
                raise
            geom = _polygon_only(shapely.make_valid(geom))
            clipped = geom.intersection(region_mask)
            repaired += 1
        if not is_points:
            clipped = _polygon_only(clipped)
        if clipped is not None and not clipped.is_empty:
            keep.append(idx)
            geometries.append(clipped)
    result = candidate.loc[keep].copy()
    result.geometry = gpd.GeoSeries(geometries, index=result.index, crs=gdf.crs)
    print(f"  {name}: candidatas_ventana={len(candidate)}, "
          f"dentro_regiones={len(result)}, reparadas={repaired}", flush=True)
    return result


def draw_polygons(ax, df, color, *, edgecolor='none', lw=0, alpha=1., z=3, simplify=0., rasterized=False):
    if df.empty:
        return
    work = df[['geometry']].copy()
    if not work.geometry.is_valid.all():
        work.geometry = work.geometry.map(lambda g: _polygon_only(shapely.make_valid(g))
                                          if g is not None and not g.is_valid else g)
        work = work.loc[work.geometry.notna() & ~work.geometry.is_empty]
    if simplify:
        work.geometry = work.geometry.simplify(simplify, preserve_topology=True)
        work = work.loc[work.geometry.notna() & ~work.geometry.is_empty]
    if work.empty:
        return
    work.plot(ax=ax, color=color, edgecolor=edgecolor,
              linewidth=lw, alpha=alpha, zorder=z, rasterized=rasterized)


def style_axis(ax, bounds):
    ax.set_xlim(bounds[0], bounds[2]); ax.set_ylim(bounds[1], bounds[3])
    ax.set_aspect('equal', adjustable='box')
    ax.set_facecolor('white'); ax.axis('off')


def build_figure(root, groupkey, layers, dpi, simplify, vector_concessions):
    group = REGION_GROUPS[groupkey]
    regions_all, oa_all, projects_all, residual_all, discounted_all = layers
    regions = region_subset(regions_all, group)
    bounds = window(regions)
    # Unión de los límites administrativos exactos, reparados si procede.
    region_parts = [_polygon_only(shapely.make_valid(g)) if not g.is_valid else g
                    for g in regions.geometry]
    region_mask = shapely.union_all(region_parts)
    region_mask = _polygon_only(shapely.make_valid(region_mask))
    if region_mask.is_empty or not region_mask.is_valid:
        raise RuntimeError(f'Máscara regional inválida: {groupkey}')

    # Select through spatial relationship, not region-string labels from OA.
    # For a border-touching feature, plotting in both regional views is expected.
    oa = clip_to_regions(oa_all, region_mask, bounds, 'OA')
    projects = clip_to_regions(projects_all, region_mask, bounds, 'COCHILCO')
    residual = clip_to_regions(residual_all, region_mask, bounds, 'residual')
    discounted = clip_to_regions(discounted_all, region_mask, bounds, 'OA descontada')

    print(f"{groupkey}: regiones={len(regions)}, OA visible={len(oa)}, "
          f"COCHILCO visible={len(projects)}, residual features={len(residual)}", flush=True)

    fig = plt.figure(figsize=(15, 10.0), facecolor='white')
    fig.text(.055, .959, f"DETALLE REGIONAL · {group['title']}", fontsize=19,
             weight='bold', color=COL['ink'], va='top')
    fig.text(.055, .925, group['subtitle'], fontsize=10, color=COL['muted'], va='top')
    fig.add_artist(Line2D([.055,.945],[.899,.899],transform=fig.transFigure,
                          color=COL['rule'],linewidth=1.2))

    labels = [
        ('01','PRESENTE (APROX.)','OA candidatas a operación'),
        ('02','FUTURO PROBABLE','COCHILCO: puntos representativos'),
        ('03','FUTURO POSIBLE','Concesión constituida: desglose provisional'),
    ]
    xs = [.055,.362,.669]; width=.274
    axes=[]
    for j, ((num, title, subtitle), x) in enumerate(zip(labels, xs)):
        fig.text(x,.872,num,fontsize=12.3,weight='bold',color=COL['muted'],va='top')
        fig.text(x+.043,.872,title,fontsize=11.2,weight='bold',color=COL['ink'],va='top')
        fig.text(x,.844,subtitle,fontsize=9.3,color=COL['muted'],va='top')
        ax=fig.add_axes([x,.18,width,.63])
        draw_polygons(ax, regions, COL['land'], edgecolor=COL['outline'], lw=.6,
                      z=1, simplify=simplify)
        style_axis(ax,bounds)
        axes.append(ax)

    draw_polygons(axes[0],oa,COL['oa'],z=3,alpha=.9)
    if not oa.empty:
        pts = oa[['geometry']].copy()
        pts.geometry = pts.geometry.representative_point()
        pts.plot(ax=axes[0], color=COL['oa'], markersize=12, edgecolor='white',
                 linewidth=.26,zorder=4)
    if not projects.empty:
        projects.plot(ax=axes[1],color=COL['project'],markersize=27,
                      edgecolor='white',linewidth=.55,zorder=4)

    draw_polygons(axes[2], residual, COL['residual'], z=2,
                  alpha=.95,simplify=simplify,rasterized=not vector_concessions)
    draw_polygons(axes[2], discounted, COL['discounted'], z=3,
                  alpha=.96,simplify=simplify,rasterized=not vector_concessions)
    draw_polygons(axes[2],regions,'none',edgecolor=COL['outline'],lw=.6,z=5,
                  simplify=simplify)
    for ax in axes:
        style_axis(ax,bounds)

    fig.legend(handles=[Line2D([],[],linestyle='',marker='o',color=COL['oa'],
                               markeredgecolor='white',markersize=7,
                               label='OA candidata (no confirmada)')],
               frameon=False,loc='center',bbox_to_anchor=(.192,.143),fontsize=9)
    fig.legend(handles=[Line2D([],[],linestyle='',marker='o',color=COL['project'],
                               markeredgecolor='white',markersize=7,
                               label='Punto de proyecto COCHILCO')],
               frameon=False,loc='center',bbox_to_anchor=(.499,.143),fontsize=9)
    fig.legend(handles=[Patch(facecolor=COL['residual'],label='Residual provisional'),
                        Patch(facecolor=COL['discounted'],label='Concesión coincidente con OA')],
               frameon=False,loc='center',bbox_to_anchor=(.818,.143),fontsize=8.5)

    fig.add_artist(Line2D([.055,.945],[.107,.107],transform=fig.transFigure,
                          color=COL['rule'],linewidth=1.1))
    fig.text(.055,.092,'Fuentes: OA y COCHILCO (selección ENMC); SERNAGEOMIN (concesiones constituidas). '
             'Proyección cartográfica EPSG:6933.', fontsize=8.7,
             color=COL['muted'],va='top')
    fig.text(.055,.071,'Lectura exploratoria: OA no confirma operación; COCHILCO no acredita huellas de proyecto. '
             'Las concesiones no identifican minerales.',fontsize=8.5,
             color=COL['ink'],va='top')
    fig.text(.055,.050,'Residual = concesión constituida menos OA candidata; '
             'no se han descontado nuevas huellas COCHILCO. '
             'Geometrías recortadas a regiones solo para visualización.',fontsize=8.4,
             color=COL['muted'],va='top')

    out = root/'outputs/figures/enmc'
    out.mkdir(parents=True,exist_ok=True)
    prefix=f'49c_detalle_{groupkey}_enmc'
    for extension in ('png','svg'):
        path=out/f'{prefix}.{extension}'
        kwargs={'dpi':dpi} if extension=='png' else {}
        fig.savefig(path,facecolor='white',**kwargs)
        print(f'  {extension.upper()}: {path}',flush=True)
    plt.close(fig)

    return dict(zona=groupkey,regiones='; '.join(regions.nomreg.astype(str)),
                n_regiones=len(regions),n_oa_visibles=len(oa),
                n_proyectos_visibles=len(projects),
                n_componentes_residual_visibles=len(residual),
                n_componentes_descontados_visibles=len(discounted),
                conteos='INTERSECCION_CON_REGIONES;_POLIGONOS_PUEDEN_CRUZAR_LIMITES',
                estado='EXPLORATORIO_OA_Y_RESIDUAL_PROVISIONALES')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--dpi',type=int,default=250)
    parser.add_argument('--simplificar-metros',type=float,default=160.,
                        help='Solo dibujo; no usar sobre geometrías analíticas')
    parser.add_argument('--vector-concesiones',action='store_true',
                        help='SVG pesado; por defecto las concesiones se rasterizan')
    args=parser.parse_args()
    root=args.root.resolve(); base=root/'data/processed/enmc'
    print('=== PASO 49c: RECORTE REGIONAL EXACTO ENMC ===',flush=True)
    layers=[read(root/'data/processed/regiones_consolidadas.gpkg'),
            read(base/'oa_enmc_candidatas.gpkg'),
            read(base/'cochilco_enmc_proyectos.gpkg'),
            read(base/'35_concesion_residual_ambito.gpkg'),
            read(base/'35_superficie_descontada_oa_ambito.gpkg')]
    regions, oa, projects, _, _ = layers
    oa=oa.loc[oa['estado_oa_provisional']=='CANDIDATA_OPERACION_POR_TIPO'].copy()
    layers[1]=oa
    if (len(regions),len(oa),len(projects)) != (16,292,55):
        raise RuntimeError(f'Conteos base inesperados: {len(regions)} regiones, '
                           f'{len(oa)} OA, {len(projects)} COCHILCO')
    if not projects.geom_type.isin(['Point','MultiPoint']).all():
        raise ValueError('COCHILCO no contiene exclusivamente puntos')
    rows=[]
    for key in ('norte','centro'):
        rows.append(build_figure(root,key,layers,args.dpi,args.simplificar_metros,
                                 args.vector_concesiones))
    dest=root/'reports/enmc/49c_control_mapas_regionales.csv'
    dest.parent.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(rows).to_csv(dest,index=False,encoding='utf-8-sig')
    print('CONTROL:',dest,flush=True)
    print('PASO 49c FINALIZADO',flush=True)

if __name__=='__main__':
    main()
