from pathlib import Path
import pandas as pd
import geopandas as gpd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports' / 'enmc'
OUT.mkdir(parents=True, exist_ok=True)
CALC = OUT / '43_ist_enmc.csv'
if not CALC.exists():
    raise FileNotFoundError(CALC)
new = pd.read_csv(CALC, encoding='utf-8-sig')
new = new.loc[new['fuente'].eq('OA_ENMC')].copy()
print(f'=== PASO 44: COMPARACION IST OA ===\nOA procesadas: {len(new)}', flush=True)

sources = [p for p in (ROOT / 'data').rglob('*.shp') if 'oa-2-articulo' in p.stem.lower()]
if not sources:
    sources = [p for p in ROOT.rglob('*.shp') if 'oa-2-articulo' in p.stem.lower() and not any(x in p.parts for x in ['.git', 'outputs'])]
if not sources:
    print('No se localizo OA-2-Articulo.shp. Buscar y copiar al proyecto.', flush=True)
    raise SystemExit(2)
source = sources[0]
orig = gpd.read_file(source, engine='pyogrio', ignore_geometry=True)
print('Fuente:', source, '| registros:', len(orig), flush=True)
print('Columnas originales:', ', '.join(orig.columns), flush=True)

fields = {str(c).upper(): c for c in orig.columns}
keys = [fields[k] for k in ('OBJECTID', 'OBJID', 'ID', 'ID_OA', 'FID', 'OID', 'OBJECTID_1') if k in fields]
if not keys:
    keys = [c for c in orig.columns if any(t in str(c).upper() for t in ('ID', 'FID'))]
checks = []
for key in keys:
    nums = pd.to_numeric(orig[key], errors='coerce')
    nonnull = nums.notna()
    matched = set(nums[nonnull].astype('int64')) & set(new['id_fuente'].astype('int64'))
    checks.append({'campo_original': key, 'cantidad_ids_coincidentes': len(matched),
                   'porcentaje_ids_coincidentes': round(len(matched) / len(new) * 100, 3),
                   'duplicados_original': int(nums[nonnull].duplicated().sum())})
checkdf = pd.DataFrame(checks)
checkdf.to_csv(OUT / '44_candidatos_clave_oa.csv', index=False, encoding='utf-8-sig')
print('\nClaves candidatas:\n', checkdf.to_string(index=False) if len(checkdf) else '(ninguna)', flush=True)
if checkdf.empty:
    print('SIN CLAVE: revisar manualmente antes de comparar.', flush=True)
    raise SystemExit(3)
best = checkdf.sort_values(['cantidad_ids_coincidentes', 'duplicados_original'], ascending=[False, True]).iloc[0]
if best['porcentaje_ids_coincidentes'] < 95 or best['duplicados_original']:
    print('NO SE COMPARA: clave no validada (coincidencia <95% o duplicada).', flush=True)
    raise SystemExit(4)
key = best['campo_original']
orig = orig.assign(id_fuente=pd.to_numeric(orig[key], errors='coerce'))
orig = orig.loc[orig.id_fuente.notna()].copy()
orig.id_fuente = orig.id_fuente.astype('int64')
# Prefix original columns to avoid collisions.
refcols = [fields[x] for x in ('IST_100', 'IST_ORIG', 'S_AP', 'S_SB', 'S_GL', 'S_HU', 'S_AI', 'S_CI', 'S_AD', 'S_PO', 'S_TU') if x in fields]
ref = orig[['id_fuente', *dict.fromkeys(refcols)]].rename(columns={c: 'original__' + str(c) for c in refcols})
comp = new.merge(ref, on='id_fuente', how='left', validate='one_to_one', indicator=True)
comp.to_csv(OUT / '44_comparacion_ist_oa.csv', index=False, encoding='utf-8-sig')
print('\nClave utilizada:', key, '| emparejadas:', int(comp['_merge'].eq('both').sum()), flush=True)
for c in refcols:
    if c.upper() not in {'IST_100', 'IST_ORIG'}:
        continue
    original = pd.to_numeric(comp['original__' + c], errors='coerce')
    delta = comp['IST_100'] - original
    valid = delta.notna()
    print(f'{c}: valores comparables={valid.sum()}, error absoluto medio={delta[valid].abs().mean():.4f}, '
          f'maximo={delta[valid].abs().max():.4f}, discrepancias >1 punto={(delta[valid].abs()>1).sum()}', flush=True)
    if valid.any():
        compare = comp.loc[valid, ['id_fuente', 'nombre', 'IST_100']].copy()
        compare['IST_original'] = original.loc[valid].to_numpy()
        compare['diferencia_puntos'] = delta.loc[valid].to_numpy()
        compare.sort_values('diferencia_puntos', key=lambda x: x.abs(), ascending=False).to_csv(
            OUT / ('44_diferencias_' + c.lower() + '.csv'), index=False, encoding='utf-8-sig')
print('PASO 44 FINALIZADO', flush=True)
