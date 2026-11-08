#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 48b: cartografia editorial exploratoria de tres estados mineros ENMC.

Reutiliza las mismas fuentes del paso 48; NO cambia datos, estados ni superficies.
El tercer panel representa la particion geométrica: residual provisional y
superficie descontada por OA. Ambas son subconjuntos de la concesion constituida.

Salidas:
 outputs/figures/enmc/48b_tres_estados_enmc.png
 outputs/figures/enmc/48b_tres_estados_enmc.svg
 reports/enmc/48b_control_cartografia.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import geopandas as gpd
import pandas as pd

EPSG = "EPSG:6933"
COLORS = {
    "outline": "#87929a", "land": "#f6f7f7", "oa": "#b15b3a",
    "project": "#176d84", "residual": "#487fa4", "discounted": "#d69a56",
    "ink": "#1c2e3b", "muted": "#5a6974", "line": "#d7dfe3",
}


def read_layer(path: Path) -> gpd.GeoDataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Falta archivo requerido: {path}")
    gdf = gpd.read_file(path, engine="pyogrio")
    if gdf.crs is None:
        raise ValueError(f"CRS ausente: {path}")
    gdf = gdf.loc[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    return gdf.to_crs(EPSG)


def polygons(ax, gdf, color, *, edge="none", lw=0, z=2, alpha=1,
             simplification=0, rasterized=False):
    if gdf.empty:
        return
    work = gdf[["geometry"]].copy()
    if simplification > 0:
        work.geometry = work.geometry.simplify(simplification, preserve_topology=True)
        work = work.loc[work.geometry.notna() & ~work.geometry.is_empty]
    if not work.empty:
        # Matplotlib uses a single artist collection when possible.
        work.plot(ax=ax, facecolor=color, edgecolor=edge, linewidth=lw,
                  alpha=alpha, zorder=z, rasterized=rasterized)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--dpi", type=int, default=240)
    p.add_argument("--simplificar-metros", type=float, default=700,
                   help="Solo cartografia; no afecta el analisis espacial")
    p.add_argument("--vector-concesiones", action="store_true",
                   help="Mantener concesiones como vector en SVG (archivo mayor)")
    args = p.parse_args()
    root = args.root.resolve()
    base = root / "data/processed/enmc"
    out = root / "outputs/figures/enmc"
    report = root / "reports/enmc"
    out.mkdir(parents=True, exist_ok=True)
    report.mkdir(parents=True, exist_ok=True)

    print("=== PASO 48b: CARTOGRAFIA EDITORIAL ENMC ===", flush=True)
    regions = read_layer(root / "data/processed/regiones_consolidadas.gpkg")
    oagdf = read_layer(base / "oa_enmc_candidatas.gpkg")
    if "estado_oa_provisional" not in oagdf:
        raise KeyError("No existe estado_oa_provisional en OA")
    oa = oagdf.loc[oagdf["estado_oa_provisional"] == "CANDIDATA_OPERACION_POR_TIPO"].copy()
    projects = read_layer(base / "cochilco_enmc_proyectos.gpkg")
    residual = read_layer(base / "35_concesion_residual_ambito.gpkg")
    constituted = read_layer(base / "35_concesiones_constituidas_ambito.gpkg")
    discounted = read_layer(base / "35_superficie_descontada_oa_ambito.gpkg")

    if (len(regions), len(oa), len(projects)) != (16, 292, 55):
        raise RuntimeError("Conteos inesperados, revisar archivos regionales/OA/COCHILCO: "
                           f"{len(regions)}, {len(oa)}, {len(projects)}")
    if not projects.geom_type.isin(["Point", "MultiPoint"]).all():
        raise ValueError("COCHILCO debe contener solo puntos representativos")

    # Comprobaciones de balance de superficies derivadas por los pasos 34-35.
    area_const = float(constituted.geometry.area.sum()/10000)
    area_res = float(residual.geometry.area.sum()/10000)
    area_disc = float(discounted.geometry.area.sum()/10000)
    err = area_const - area_res - area_disc
    print(f"Balance: concesiones={area_const:,.2f} ha; residual={area_res:,.2f} ha; "
          f"OA descontada={area_disc:,.2f} ha; error={err:.4f} ha", flush=True)
    if abs(err) > 1:
        raise RuntimeError("Balance de superficies inconsistente (>1 ha)")

    # Distribucion fija: la cabecera, los paneles y los pies no comparten espacio.
    fig = plt.figure(figsize=(14.2, 13.3), facecolor="white")
    fig.text(.05, .972, "TRES ESTADOS DEL ESPACIO MINERO EN CHILE",
             ha="left", va="top", fontsize=19, weight="bold", color=COLORS["ink"])
    fig.text(.05, .948, "Geografia exploratoria de minerales criticos · Ambito de 343 comunas",
             ha="left", va="top", fontsize=10.5, color=COLORS["muted"])
    fig.add_artist(Line2D([.05, .95], [.928, .928], transform=fig.transFigure,
                          color=COLORS["line"], linewidth=1.2))

    entries = [
        ("01", "PRESENTE", "OA · 292 candidatos a operacion"),
        ("02", "FUTURO PROBABLE", "COCHILCO · 55 puntos de proyecto"),
        ("03", "FUTURO POSIBLE", "Concesiones y residual provisional"),
    ]
    boxes = [(0.048, .157, .287, .69), (0.357, .157, .287, .69), (0.666, .157, .287, .69)]
    axes = []
    bbox = regions.total_bounds
    xmin, ymin, xmax, ymax = [float(v) for v in bbox]
    dx, dy = xmax-xmin, ymax-ymin

    for i, ((num, heading, subtitle), (x, y, w, h)) in enumerate(zip(entries, boxes)):
        fig.text(x, .908, num, fontsize=14, weight="bold", color=COLORS["muted"], va="top")
        fig.text(x+.04, .908, heading, fontsize=12.0, weight="bold", color=COLORS["ink"], va="top")
        fig.text(x, .884, subtitle, fontsize=9.4, color=COLORS["muted"], va="top")
        ax = fig.add_axes([x, y, w, h])
        ax.set_facecolor("white")
        polygons(ax, regions, COLORS["land"], edge=COLORS["outline"], lw=.28,
                 z=1, simplification=args.simplificar_metros)
        ax.set_xlim(xmin-.08*dx, xmax+.08*dx)
        ax.set_ylim(ymin-.025*dy, ymax+.025*dy)
        ax.set_aspect("equal", adjustable="box")
        ax.axis("off")
        axes.append(ax)

    polygons(axes[0], oa, COLORS["oa"], z=3, alpha=.9)
    locators = oa[["geometry"]].copy()
    locators.geometry = locators.geometry.representative_point()
    locators.plot(ax=axes[0], color=COLORS["oa"], markersize=3.6,
                  edgecolor="white", linewidth=.10, alpha=.90, zorder=4)
    projects.plot(ax=axes[1], color=COLORS["project"], markersize=16,
                  edgecolor="white", linewidth=.42, alpha=.95, zorder=4)

    # Tercer estado: cobertura residual y superficie OA descontada son partes
    # de la concesion constituida. No presentar residual como capa adicional.
    raster = not args.vector_concesiones
    polygons(axes[2], residual, COLORS["residual"], z=2, alpha=.94,
             simplification=args.simplificar_metros, rasterized=raster)
    polygons(axes[2], discounted, COLORS["discounted"], z=3, alpha=.95,
             simplification=args.simplificar_metros, rasterized=raster)
    polygons(axes[2], regions, "none", edge=COLORS["outline"], lw=.28,
             z=5, simplification=args.simplificar_metros)

    # Legends: separate fixed lower band avoids collision with Chile outline.
    legend_y = .126
    fig.legend(handles=[Line2D([], [], marker="o", linestyle="", color=COLORS["oa"],
                               markeredgecolor="white", markersize=8,
                               label="OA candidata (no confirmada)")],
               loc="center", bbox_to_anchor=(.191, legend_y), frameon=False, fontsize=9)
    fig.legend(handles=[Line2D([], [], marker="o", linestyle="", color=COLORS["project"],
                               markeredgecolor="white", markersize=8,
                               label="Punto representativo")],
               loc="center", bbox_to_anchor=(.50, legend_y), frameon=False, fontsize=9)
    fig.legend(handles=[Patch(facecolor=COLORS["residual"], label="Concesion residual"),
                        Patch(facecolor=COLORS["discounted"], label="OA descontada")],
               loc="center", bbox_to_anchor=(.806, legend_y), frameon=False,
               fontsize=8.5, ncol=1, labelspacing=.5)

    fig.add_artist(Line2D([.05, .95], [.094, .094], transform=fig.transFigure,
                          color=COLORS["line"], linewidth=1.1))
    fig.text(.05, .078,
             "Fuentes: OA y COCHILCO (seleccion ENMC); SERNAGEOMIN (todas las concesiones constituidas). "
             "Proyeccion cartografica: EPSG:6933.",
             ha="left", va="top", fontsize=8.7, color=COLORS["muted"])
    fig.text(.05, .058,
             "Lectura exploratoria: OA no confirma operacion; COCHILCO representa localizaciones, no huellas. "
             "Concesiones sin atribucion de mineral.",
             ha="left", va="top", fontsize=8.5, color=COLORS["ink"])
    fig.text(.05, .038,
             "Residual provisional = concesion constituida menos OA candidata. No descuenta nuevas huellas "
             "COCHILCO ni acredita ausencia de actividad minera.",
             ha="left", va="top", fontsize=8.3, color=COLORS["muted"])

    png = out / "48b_tres_estados_enmc.png"
    svg = out / "48b_tres_estados_enmc.svg"
    fig.savefig(png, dpi=args.dpi, facecolor="white")
    fig.savefig(svg, facecolor="white")
    plt.close(fig)

    control = pd.DataFrame([
        {"capa": "regiones", "registros": len(regions), "area_ha": None, "estado": "BASE"},
        {"capa": "OA_ENMC", "registros": len(oa), "area_ha": None, "estado": "CANDIDATA_NO_CONFIRMADA"},
        {"capa": "COCHILCO_ENMC", "registros": len(projects), "area_ha": None, "estado": "PUNTOS_REPRESENTATIVOS"},
        {"capa": "concesiones_constituidas", "registros": len(constituted), "area_ha": area_const, "estado": "SIN_ATRIBUCION_MINERAL"},
        {"capa": "concesion_residual", "registros": len(residual), "area_ha": area_res, "estado": "PROVISIONAL"},
        {"capa": "OA_descontada", "registros": len(discounted), "area_ha": area_disc, "estado": "PROVISIONAL"},
    ])
    control.to_csv(report / "48b_control_cartografia.csv", index=False, encoding="utf-8-sig")
    print("OA=292; COCHILCO=55; regiones=16", flush=True)
    print("PNG:", png, flush=True)
    print("SVG:", svg, flush=True)
    print("CONTROL:", report / "48b_control_cartografia.csv", flush=True)
    print("PASO 48b FINALIZADO", flush=True)

if __name__ == "__main__":
    main()
