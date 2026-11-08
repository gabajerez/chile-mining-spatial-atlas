#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 62: audita compatibilidad de los ambitos 58 (comunas) y 61 (regiones).

No altera datos ni recalcula las intersecciones de humedales.
Lee el control 61 y 58; compara geométricamente sus mascaras en EPSG:6933.
"""
from __future__ import annotations
import json
from pathlib import Path
import unicodedata
from datetime import datetime, timezone
import geopandas as gpd
import pandas as pd
import shapely

ROOT = Path(__file__).resolve().parents[1]
CRS = 'EPSG:6933'
ZONES = {
    'norte': ('arica y parinacota', 'tarapaca', 'antofagasta', 'atacama', 'coquimbo'),
    'centro': ('valparaiso', 'metropolitana', 'ohiggins'),
}

def norm(value):
    txt = unicodedata.normalize('NFKD', str(value).lower())
    return ''.join(c for c in txt if c.isalnum() and not unicodedata.combining(c))

def valid_polygon(g):
    if g is None or g.is_empty:
        return shapely.GeometryCollection()
    if not g.is_valid:
        g = shapely.make_valid(g)
    if g.geom_type in ('Polygon', 'MultiPolygon'):
        return g
    parts = [p for p in shapely.get_parts(g) if p.geom_type in ('Polygon', 'MultiPolygon') and not p.is_empty]
    return shapely.union_all(parts) if parts else shapely.GeometryCollection()

def union_of(gdf):
    return valid_polygon(shapely.union_all([valid_polygon(g) for g in gdf.geometry]))

def main():
    print('=== PASO 62: AUDITORIA AMBITOS 58 VS 61 ===', flush=True)
    reps = ROOT / 'reports' / 'enmc'
    reg = gpd.read_file(ROOT/'data/processed/regiones_consolidadas.gpkg', engine='pyogrio').to_crs(CRS)
    com = gpd.read_file(ROOT/'data/processed/comunas_consolidadas.gpkg', engine='pyogrio').to_crs(CRS)
    if len(reg) != 16 or len(com) != 343 or 'nomreg' not in reg:
        raise ValueError('Universo de regiones/comunas o columnas inesperado')
    domain = union_of(com)
    names = reg.nomreg.map(norm)
    masks = {}
    for zone, targets in ZONES.items():
        ids = []
        for target in targets:
            matches = reg.index[names.str.contains(norm(target), regex=False)].tolist()
            if len(matches) != 1:
                raise ValueError(f'Region no unica {target}: {matches}')
            ids.extend(matches)
        masks[zone] = union_of(reg.loc[ids])
    local = pd.read_csv(reps/'61_control_overlap_cartografico_mma.csv', encoding='utf-8-sig')
    national = pd.read_csv(reps/'58_overlap_humedales_mma_resumen.csv', encoding='utf-8-sig')
    if len(national) != 1:
        raise ValueError('Se esperaba una fila en reporte 58')
    required = {'zona','componente','sensible_ha','concesionada_ha','residual_ha'}
    if not required.issubset(local.columns):
        raise ValueError(f'Faltan columnas en 61: {sorted(required-set(local.columns))}')
    if local.duplicated(['zona','componente']).any():
        raise ValueError('Duplicados por zona/componente en 61')
    area_ha = lambda g: g.area / 10_000.
    records = []
    for zone, mask in masks.items():
        inside = valid_polygon(mask.intersection(domain))
        outside = valid_polygon(mask.difference(domain))
        zone_area = area_ha(mask)
        outside_ha = area_ha(outside)
        values = local[(local.zona == zone) & (local.componente == 'humedales')]
        if len(values) != 1:
            raise ValueError(f'No hay un registro humedales para {zone}')
        values = values.iloc[0]
        row = {
            'zona': zone,
            'area_mascara_regional_ha': zone_area,
            'area_dentro_ambito_comunal_ha': area_ha(inside),
            'area_fuera_ambito_comunal_ha': outside_ha,
            'porcentaje_mascara_fuera_ambito': 100 * outside_ha / zone_area if zone_area else None,
            'humedales_61_ha': float(values.sensible_ha),
            'humedales_concesionados_61_ha': float(values.concesionada_ha),
            'humedales_residuales_61_ha': float(values.residual_ha),
            'porcentaje_humedales_61': 100 * float(values.concesionada_ha) / float(values.sensible_ha) if values.sensible_ha else None,
            'ambito_regional_equivalente_al_comunal': outside_ha <= max(1.0, zone_area * 1e-8),
        }
        records.append(row)
        print(f"{zone}: mascara={zone_area:,.2f} ha; FUERA de 343 comunas={outside_ha:,.2f} ha ({row['porcentaje_mascara_fuera_ambito']:.5f}%)",flush=True)
    union_mask = valid_polygon(shapely.union_all(list(masks.values())))
    overlap = area_ha(valid_polygon(masks['norte'].intersection(masks['centro'])))
    if overlap > 1.0:
        raise ValueError(f'Zonas norte/centro se solapan en {overlap} ha')
    national_h = float(national.iloc[0].superficie_sensible_unica_ha)
    national_c = float(national.iloc[0].superficie_sensible_concesionada_ha)
    h_total = sum(r['humedales_61_ha'] for r in records)
    c_total = sum(r['humedales_concesionados_61_ha'] for r in records)
    if c_total > national_c + 0.01 or h_total > national_h + 0.01:
        print('ATENCION: sumas 61 exceden 58; comprobar ambitos y procesamiento antes de interpretar.', flush=True)
    else:
        print('Suma humedales norte+centro NO excede el total del paso 58; esto no prueba igualdad de denominadores.', flush=True)
    result = {
        'paso': 62,
        'fecha_utc': datetime.now(timezone.utc).isoformat(),
        'resultado': 'AUDITORIA_DE_MASCARAS_NO_RECALCULA_HUMEDALES',
        'ambito_nacional_comunal_ha': area_ha(domain),
        'norte_centro_solapamiento_ha': overlap,
        'norte_centro_dentro_comunas_ha': area_ha(valid_polygon(union_mask.intersection(domain))),
        'humedales_58_ambito_comunal_ha': national_h,
        'concesionados_58_ambito_comunal_ha': national_c,
        'humedales_61_norte_centro_ha': h_total,
        'concesionados_61_norte_centro_ha': c_total,
        'nota': 'Si alguna mascara regional tiene area fuera del ambito comunal, los porcentajes 61 requieren homologacion de mascara antes de compararlos rigurosamente con 58. Aun con mascaras iguales, falta control territorial sur.',
    }
    reps.mkdir(parents=True, exist_ok=True)
    csv = reps/'62_auditoria_ambitos_58_61.csv'
    js = reps/'62_auditoria_ambitos_58_61.json'
    pd.DataFrame(records).to_csv(csv,index=False,encoding='utf-8-sig')
    js.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('CSV:',csv,flush=True)
    print('JSON:',js,flush=True)
    print('PASO 62 FINALIZADO',flush=True)

if __name__ == '__main__':
    main()
