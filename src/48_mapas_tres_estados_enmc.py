#!/usr/bin/env python3
"""Paso 48: mapa exploratorio reproducible de tres estados del espacio mineral ENMC.

Salidas: outputs/figures/enmc/48_tres_estados_enmc.png y .svg,
         reports/enmc/48_control_cartografia.csv.

Nota: OA = candidatos no confirmados; COCHILCO = puntos representativos;
residual concesional = provisional (sin nuevas huellas COCHILCO verificadas).
No infiere el mineral asociado a concesiones.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
import geopandas as gpd
import pandas as pd

CRS = 'EPSG:6933'


def load(path: Path) -> gpd.GeoDataFrame:
    if not path.exists():
        raise FileNotFoundError(f'No existe capa requerida: {path}')
    frame = gpd.read_file(path, engine='pyogrio')
    if frame.crs is None:
        raise ValueError(f'Capa sin CRS: {path}')
    frame = frame.loc[frame.geometry.notna() & ~frame.geometry.is_empty].copy()
    return frame.to_crs(CRS)


def vector_plot(ax, frame, *, facecolor, edgecolor, linewidth, zorder, alpha=1.0, tol=0):
    if frame.empty:
        return
    frame = frame[['geometry']].copy()
    if tol:
        frame.geometry = frame.geometry.simplify(tol, preserve_topology=True)
    frame.plot(ax=ax, facecolor=facecolor, edgecolor=edgecolor,
               linewidth=linewidth, zorder=zorder, alpha=alpha)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--dpi', type=int, default=210)
    parser.add_argument('--simplificar-metros', type=float, default=900,
                        help='Simplificacion SOLO para visualizacion, no modifica datos ni calculos')
    args = parser.parse_args()
    root = args.root.resolve()
    base = root / 'data' / 'processed' / 'enmc'
    regions_path = root / 'data' / 'processed' / 'regiones_consolidadas.gpkg'
    if not regions_path.exists():
        raise FileNotFoundError(regions_path)
    out = root / 'outputs' / 'figures' / 'enmc'
    report = root / 'reports' / 'enmc'
    out.mkdir(parents=True, exist_ok=True)
    report.mkdir(parents=True, exist_ok=True)

    print('=== PASO 48: CARTOGRAFIA DE TRES ESTADOS ===', flush=True)
    regions = load(regions_path)
    oa_all = load(base / 'oa_enmc_candidatas.gpkg')
    if 'estado_oa_provisional' not in oa_all.columns:
        raise ValueError('No existe estado_oa_provisional en OA')
    oa = oa_all.loc[oa_all.estado_oa_provisional == 'CANDIDATA_OPERACION_POR_TIPO'].copy()
    projects = load(base / 'cochilco_enmc_proyectos.gpkg')
    residual = load(base / '35_concesion_residual_ambito.gpkg')
    constituted = load(base / '35_concesiones_constituidas_ambito.gpkg')

    if len(oa) != 292 or len(projects) != 55 or len(regions) != 16:
        raise RuntimeError(f'Conteos inesperados: OA={len(oa)}; COCHILCO={len(projects)}; regiones={len(regions)}')
    if not projects.geom_type.isin(['Point','MultiPoint']).all():
        raise ValueError('COCHILCO: geometria distinta a punto. Revisar metodologia')

    bounds = regions.total_bounds
    xmin, ymin, xmax, ymax = bounds
    padx = (xmax-xmin)*0.05
    pady = (ymax-ymin)*0.025
    fig, axs = plt.subplots(1, 3, figsize=(13.0, 12.0), sharex=True, sharey=True)
    fig.patch.set_facecolor('white')

    panels = [
        ('01 · Presente operativo (aproximación)', '292 polígonos OA: candidatos, sin operación confirmada'),
        ('02 · Futuro probable (inversión)', '55 proyectos COCHILCO: puntos representativos'),
        ('03 · Futuro posible (derechos)', 'Concesiones constituidas y residual provisional'),
    ]
    for ax, (title, subtitle) in zip(axs, panels):
        ax.set_facecolor('#fafafa')
        vector_plot(ax, regions, facecolor='#f4f5f6', edgecolor='#a1a7aa', linewidth=.45, zorder=1,
                    tol=args.simplificar_metros)
        ax.set_title(title, fontsize=12.5, weight='bold', loc='left', pad=15)
        ax.text(0, 1.005, subtitle, transform=ax.transAxes, va='bottom', ha='left', fontsize=8.0, color='#555')
        ax.set_xlim(xmin-padx, xmax+padx)
        ax.set_ylim(ymin-pady, ymax+pady)
        ax.set_aspect('equal', adjustable='box')
        ax.set_axis_off()

    vector_plot(axs[0], oa, facecolor='#b46c43', edgecolor='#995934', linewidth=.1, zorder=4, alpha=.85)
    # Las huellas OA pequeñas podrían no ser visibles a escala nacional: puntos localizadores derivativos.
    centers = oa.copy()
    centers.geometry = centers.geometry.representative_point()
    centers.plot(ax=axs[0], color='#a14c2c', markersize=2.3, alpha=.8, zorder=5)

    projects.plot(ax=axs[1], color='#156b85', markersize=11, marker='o',
                  edgecolor='white', linewidth=.3, alpha=.92, zorder=5)

    # Dibujar cobertura nacional concesional simplificada SOLO para visualización.
    vector_plot(axs[2], constituted, facecolor='#cad5df', edgecolor='none', linewidth=0,
                zorder=2, alpha=.9, tol=args.simplificar_metros)
    vector_plot(axs[2], residual, facecolor='#477ea5', edgecolor='none', linewidth=0,
                zorder=3, alpha=.94, tol=args.simplificar_metros)
    # Límites regionales por encima de capas.
    vector_plot(axs[2], regions, facecolor='none', edgecolor='#646d72', linewidth=.35, zorder=6,
                tol=args.simplificar_metros)

    axs[0].legend(handles=[Line2D([], [], marker='o', linestyle='', color='#a14c2c', markersize=6,
                                  label='OA candidata (no confirmada)')],
                  loc='lower center', bbox_to_anchor=(.5, -.018), fontsize=8, frameon=False)
    axs[1].legend(handles=[Line2D([], [], marker='o', linestyle='', color='#156b85', markersize=6,
                                  label='Proyecto (punto representativo)')],
                  loc='lower center', bbox_to_anchor=(.5, -.018), fontsize=8, frameon=False)
    axs[2].legend(handles=[Patch(facecolor='#477ea5', label='Residual provisional'),
                            Patch(facecolor='#cad5df', label='Concesión constituida')],
                  loc='lower center', bbox_to_anchor=(.5, -.045), fontsize=8, frameon=False, ncol=1)

    fig.suptitle('Chile · Tres estados del espacio minero asociados al análisis ENMC',
                 x=.5, y=.97, fontsize=16, weight='bold')
    fig.text(.5, .035,
        'Ámbito: 343 comunas · Proyección de mapa EPSG:6933 · OA y COCHILCO: selección ENMC; '
        'concesiones: todas las constituidas, sin atribución mineral.',
        ha='center', fontsize=8, color='#3b4346')
    fig.text(.5, .017,
        'FIGURA EXPLORATORIA: no implica operación confirmada, huella futura verificada ni impacto ambiental. '
        'El residual no descuenta nuevos polígonos COCHILCO.',
        ha='center', fontsize=7.6, color='#8a3f24')
    fig.subplots_adjust(left=.018, right=.982, bottom=.07, top=.93, wspace=.06)
    png = out/'48_tres_estados_enmc.png'
    svg = out/'48_tres_estados_enmc.svg'
    fig.savefig(png, dpi=args.dpi, facecolor='white', bbox_inches='tight')
    fig.savefig(svg, facecolor='white', bbox_inches='tight')
    plt.close(fig)

    stats = pd.DataFrame([
        {'capa':'regiones','registros':len(regions),'uso':'limite del mapa','estado':'BASE'},
        {'capa':'OA_ENMC','registros':len(oa),'uso':'estado 1','estado':'CANDIDATA_NO_CONFIRMADA'},
        {'capa':'COCHILCO_ENMC','registros':len(projects),'uso':'estado 2','estado':'PUNTO_REPRESENTATIVO'},
        {'capa':'concesiones_constituidas','registros':len(constituted),'uso':'estado 3 base','estado':'CONSTITUIDAS_SIN_MINERAL'},
        {'capa':'residual','registros':len(residual),'uso':'estado 3 residual','estado':'PROVISIONAL'},
    ])
    stats.to_csv(report/'48_control_cartografia.csv', index=False, encoding='utf-8-sig')
    print(f'OA={len(oa)}; COCHILCO={len(projects)}; regiones={len(regions)}', flush=True)
    print('PNG:', png, flush=True)
    print('SVG:', svg, flush=True)
    print('Control:', report/'48_control_cartografia.csv', flush=True)
    print('PASO 48 FINALIZADO', flush=True)

if __name__ == '__main__':
    main()
