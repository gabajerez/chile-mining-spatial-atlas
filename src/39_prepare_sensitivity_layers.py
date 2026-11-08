"""Paso 39: prepara las 11 variables de sensibilidad del atlas ENMC.

No calcula el IST ni presupone que las capas representan impactos.
Utiliza el inventario 38, registra procedencia, repara geometrías,
convierte geometrías Z a 2D, reproyecta a EPSG:6933 y recorta a
las 343 comunas del ámbito del artículo. Excluye archivos duplicados
alternativos de turismo para mantener trazabilidad.
"""
from pathlib import Path
import unicodedata
import pandas as pd
import geopandas as gpd
import shapely

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data' / 'raw' / 'sensibilidad'
MANIFEST = ROOT / 'reports' / 'enmc' / '38_inventario_sensibilidad.csv'
COMUNAS = ROOT / 'data' / 'processed' / 'comunas_consolidadas.gpkg'
OUTPUT = ROOT / 'data' / 'processed' / 'enmc' / 'sensibilidad'
REPORT = ROOT / 'reports' / 'enmc'
TARGET = 'EPSG:6933'
OUTPUT.mkdir(parents=True, exist_ok=True)
REPORT.mkdir(parents=True, exist_ok=True)

# Los nombres provienen del inventario 38; no se concatenan versiones alternativas.
SOURCES = {
    'areas_protegidas': 'areas protegidas.shp',
    'sitios_prioritarios': 'Sitios prioritarios.shp',
    'reservas_biosfera': 'l_43_v1_reserva_de_la_biosfera.shp',
    'glaciares': 'glaciares.shp',
    'humedales': 'Humedales.shp',
    'planes_atmosfericos': 'planes de descontaminacion.shp',
    'comunidades_indigenas': 'Comunidades indigenas.shp',
    'areas_desarrollo_indigena': 'ADI.shp',
    'areas_pobladas': 'Areas pobladas.shp',
    'atractivos_turisticos': 'Atractivos Turísticos.shp',
    'zonas_interes_turistico': 'Zonas de interés  turístico.shp',
}

COMPONENTS = {
    'areas_protegidas': 'areas_protegidas',
    'sitios_prioritarios': 'sitios_y_biosfera',
    'reservas_biosfera': 'sitios_y_biosfera',
    'glaciares': 'glaciares',
    'humedales': 'humedales',
    'planes_atmosfericos': 'planes_atmosfericos',
    'comunidades_indigenas': 'comunidades_indigenas',
    'areas_desarrollo_indigena': 'areas_desarrollo_indigena',
    'areas_pobladas': 'areas_pobladas',
    'atractivos_turisticos': 'turismo',
    'zonas_interes_turistico': 'turismo',
}

POLYGON_TYPES = {'Polygon', 'MultiPolygon'}
POINT_TYPES = {'Point', 'MultiPoint'}

def normalize(s):
    s = unicodedata.normalize('NFKD', str(s).casefold())
    return ''.join(c for c in s if not unicodedata.combining(c))


def polygonal(geom):
    if geom is None or geom.is_empty:
        return shapely.GeometryCollection()
    geom = shapely.force_2d(geom)
    if not shapely.is_valid(geom):
        geom = shapely.make_valid(geom)
    parts = []
    for part in shapely.get_parts(geom):
        if part.geom_type in POLYGON_TYPES and not part.is_empty:
            parts.append(part)
    return shapely.union_all(parts) if parts else shapely.GeometryCollection()


def normalize_geometry(geom, mode):
    if geom is None or geom.is_empty:
        return None
    geom = shapely.force_2d(geom)
    if not shapely.is_valid(geom):
        geom = shapely.make_valid(geom)
    if mode == 'polygon':
        result = polygonal(geom)
    else:
        parts = [p for p in shapely.get_parts(geom)
                 if p.geom_type in POINT_TYPES and not p.is_empty]
        result = shapely.union_all(parts) if parts else shapely.GeometryCollection()
    return None if result.is_empty else result


def select_source(manifest, category, basename):
    rows = manifest.loc[manifest['categoria'].eq(category)].copy()
    rows = rows.loc[rows['archivo'].map(lambda x: normalize(Path(str(x).replace('\\', '/')).name)) == normalize(basename)]
    rows = rows.loc[rows['estado'].eq('OK')]
    if len(rows) != 1:
        raise RuntimeError(f'{category}: se esperaban 1 archivo {basename!r}, hay {len(rows)}. Revisar inventario.')
    relative_path = str(rows.iloc[0]['archivo']).replace('\\', '/')
    path = BASE.joinpath(*relative_path.split('/'))
    if not path.is_file():
        raise FileNotFoundError(path)
    return path, rows.iloc[0]


def main():
    manifest = pd.read_csv(MANIFEST, encoding='utf-8-sig').fillna('')
    communes = gpd.read_file(COMUNAS, engine='pyogrio')
    if communes.crs is None or len(communes) != 343:
        raise RuntimeError('Comunas sin CRS o recuento distinto de 343')
    communes = communes.to_crs(TARGET)
    territory = polygonal(shapely.union_all([polygonal(g) for g in communes.geometry]))
    if territory.is_empty:
        raise RuntimeError('Ambito comunal vacio')
    bounds = territory.bounds
    summary = []
    print('=== PASO 39: NORMALIZACION SENSIBILIDAD ===', flush=True)
    print('Ambito comunal (ha):', round(territory.area / 10000, 2), flush=True)

    for category, filename in SOURCES.items():
        path, inventory = select_source(manifest, category, filename)
        src = gpd.read_file(path, engine='pyogrio')
        if src.crs is None:
            raise RuntimeError(f'{category}: falta CRS')
        source_count = len(src)
        if source_count != int(inventory['registros']):
            raise RuntimeError(f'{category}: cambió el conteo desde la auditoría 38')
        shape = str(inventory['geometria'])
        mode = 'point' if 'Point' in shape else 'polygon'
        src['geometry'] = src.geometry.map(lambda g: normalize_geometry(g, mode))
        src = src.loc[src.geometry.notna() & ~src.geometry.is_empty].copy()
        valid_count = len(src)
        src = src.to_crs(TARGET)

        # bbox + índice espacial: solo candidatos antes de intersección costosa
        candidates = src.iloc[src.sindex.query(territory, predicate='intersects')].copy()
        if not candidates.empty:
            candidates['geometry'] = candidates.geometry.map(lambda g: g.intersection(territory))
            candidates = candidates.loc[~candidates.geometry.is_empty].copy()
            candidates['geometry'] = candidates.geometry.map(lambda g: normalize_geometry(g, mode))
            candidates = candidates.loc[candidates.geometry.notna() & ~candidates.geometry.is_empty].copy()

        # No ejecutar silenciosamente sobre capas sin cobertura espacial
        if candidates.empty:
            raise RuntimeError(f'{category}: ninguna geometría intersecta las comunas. Revisar CRS y fuente.')

        # Evitar campos conflictivos de Shapefile; conservar las fuentes por separado.
        candidates = candidates[['geometry']].copy()
        candidates.insert(0, 'source_id', range(1, len(candidates) + 1))
        candidates['categoria'] = category
        candidates['componente'] = COMPONENTS[category]
        if mode == 'polygon':
            candidates['area_ha'] = candidates.geometry.area / 10000.0
        else:
            candidates['area_ha'] = 0.0
        dest = OUTPUT / f'39_{category}.gpkg'
        if dest.exists():
            dest.unlink()
        candidates.to_file(dest, layer=category, driver='GPKG', engine='pyogrio')
        total_geom_area = float(candidates['area_ha'].sum())
        summary.append({
            'categoria': category,
            'componente_ist': COMPONENTS[category],
            'archivo_origen': str(path.relative_to(ROOT)),
            'crs_origen': str(inventory['crs']),
            'tipo_origen': shape,
            'tipo_analisis': mode,
            'n_origen': source_count,
            'n_geometria_valida': valid_count,
            'n_intersectan_ambito': len(candidates),
            'suma_area_ha_no_disuelta': total_geom_area,
            'destino': str(dest.relative_to(ROOT)),
            'nota': 'Suma no disuelta: no usar como denominador areal sin union geométrica' if mode == 'polygon' else 'Puntos: no usar como superficie',
        })
        print(f'{category}: {source_count} origen -> {len(candidates)} en ámbito | {mode}', flush=True)

    report = pd.DataFrame(summary)
    report_path = REPORT / '39_normalizacion_sensibilidad_resumen.csv'
    report.to_csv(report_path, index=False, encoding='utf-8-sig')
    assert len(report) == 11
    assert report['componente_ist'].nunique() == 9
    print('REPORTE:', report_path, flush=True)
    print('PASO 39 FINALIZADO', flush=True)


if __name__ == '__main__':
    main()
