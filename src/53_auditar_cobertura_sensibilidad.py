"""Paso 53: auditoria de cobertura geografica de las 11 fuentes sensibles.

No infiere completitud: reporta presencia espacial y posibles alertas.
No modifica geometrias ni resultados de pasos anteriores.
"""
from pathlib import Path
import argparse
import sys

import geopandas as gpd
import pandas as pd

CAPAS = [
    'areas_protegidas', 'sitios_prioritarios', 'reservas_biosfera',
    'glaciares', 'humedales', 'planes_atmosfericos',
    'comunidades_indigenas', 'areas_desarrollo_indigena',
    'areas_pobladas', 'atractivos_turisticos', 'zonas_interes_turistico',
]


def leer(ruta):
    if not ruta.exists():
        raise FileNotFoundError(f'Falta archivo: {ruta}')
    gdf = gpd.read_file(ruta, engine='pyogrio')
    if gdf.crs is None:
        raise ValueError(f'CRS ausente: {ruta}')
    return gdf.to_crs('EPSG:6933')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    inp = root / 'data/processed/enmc/sensibilidad'
    out = root / 'reports/enmc'
    out.mkdir(parents=True, exist_ok=True)
    admin = leer(root / 'data/processed/regiones_consolidadas.gpkg')
    if 'nomreg' not in admin.columns:
        raise ValueError(f'Regiones sin nomreg: {list(admin.columns)}')
    admin = admin.loc[admin.geometry.notna() & ~admin.geometry.is_empty, ['nomreg','geometry']].copy()
    admin['geometry'] = admin.geometry.make_valid()
    # Agrupar evita contar subdivisiones de la misma region varias veces.
    regiones = admin.dissolve(by='nomreg').reset_index().sort_values('nomreg').reset_index(drop=True)
    print(f'=== PASO 53: AUDITORIA DE COBERTURA DE {len(CAPAS)} CAPAS ===', flush=True)
    print(f'Regiones: {len(regiones)} | CRS: EPSG:6933', flush=True)
    if len(regiones) != 16:
        raise ValueError(f'Se esperaban 16 regiones, se obtuvieron {len(regiones)}')

    filas = []
    resumen = []
    for nombre in CAPAS:
        ruta = inp / f'39_{nombre}.gpkg'
        g = leer(ruta)
        g = g.loc[g.geometry.notna() & ~g.geometry.is_empty, ['geometry']].copy()
        invalidas = int((~g.geometry.is_valid).sum())
        if invalidas:
            print(f'  {nombre}: {invalidas} geometrías inválidas; reparando solo en memoria', flush=True)
            g['geometry'] = g.geometry.make_valid()
            g = g.loc[g.geometry.notna() & ~g.geometry.is_empty].copy()
        total = len(g)
        sindex = g.sindex
        presente = []
        for r in regiones.itertuples(index=False):
            # Intersects cuenta una entidad en todas las regiones que toca.
            indices = sindex.query(r.geometry, predicate='intersects')
            n = len(indices)
            if n:
                presente.append(r.nomreg)
            filas.append({
                'capa': nombre,
                'region': r.nomreg,
                'n_geometrias_intersectan': n,
                'n_total_capa': total,
                'presencia_geometrica': bool(n),
            })
        n_reg = len(presente)
        flag = ('REVISAR_COBERTURA_GEOGRAFICA' if n_reg <= 3
                else 'REVISAR_FUENTE_Y_COMPLETITUD')
        resumen.append({
            'capa': nombre, 'n_geometrias': total,
            'n_regiones_con_presencia': n_reg,
            'regiones_con_presencia': ' | '.join(presente),
            'geometrias_invalidas_antes_reparacion': invalidas,
            'revision_requerida': flag,
            'nota': 'Ausencia en una region no demuestra ausencia real del componente. '
                    'Presencia en muchas regiones tampoco certifica cobertura nacional completa.'
        })
        print(f'  {nombre}: {total} entidades | regiones con presencia: {n_reg}/16 | {flag}', flush=True)

    pd.DataFrame(filas).to_csv(out/'53_cobertura_sensibilidad_por_region.csv', index=False, encoding='utf-8-sig')
    res = pd.DataFrame(resumen).sort_values(['n_regiones_con_presencia','capa'])
    res.to_csv(out/'53_alertas_cobertura_sensibilidad.csv', index=False, encoding='utf-8-sig')
    print('\n=== CAPAS A PRIORIZAR PARA VERIFICACION DE FUENTE ===', flush=True)
    print(res[['capa','n_geometrias','n_regiones_con_presencia']].to_string(index=False), flush=True)
    print('Reportes: 53_cobertura_sensibilidad_por_region.csv; 53_alertas_cobertura_sensibilidad.csv', flush=True)
    print('PASO 53 FINALIZADO', flush=True)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'ERROR: {e}', file=sys.stderr)
        raise
