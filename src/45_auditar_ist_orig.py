"""Paso 45: audita codigos especiales de IST_ORIG y reproduce comparacion por componente.
No altera datos ni sustituye codigos; escribe CSV de diagnostico.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports' / 'enmc'
OUT.mkdir(parents=True, exist_ok=True)
SRC = next((p for p in ROOT.rglob('OA-2-Articulo.shp') if '.git' not in p.parts), None)
if SRC is None:
    raise FileNotFoundError('OA-2-Articulo.shp')
CALC = OUT / '43_ist_enmc.csv'
if not CALC.is_file():
    raise FileNotFoundError(CALC)
old = gpd.read_file(SRC, engine='pyogrio', ignore_geometry=True)
new = pd.read_csv(CALC, encoding='utf-8-sig')
new = new.loc[new.fuente.eq('OA_ENMC')].copy()
old['OBJECTID'] = pd.to_numeric(old.OBJECTID, errors='coerce')
new['OBJECTID'] = pd.to_numeric(new.id_fuente, errors='coerce')
assert old['OBJECTID'].notna().all() and not old.OBJECTID.duplicated().any()
assert new['OBJECTID'].notna().all() and not new.OBJECTID.duplicated().any()
cols = ['OBJECTID','NOMBRE','IST_100','IST_ORIG','IST_01'] + [f'S_{s}' for s in ['AP','SB','GL','HU','AI','CI','AD','PO','TU'] if f'S_{s}' in old]
merge = new.merge(old[cols].rename(columns={c:'original_'+c for c in cols if c!='OBJECTID'}),on='OBJECTID',validate='one_to_one',indicator=True)
if len(merge)!=292 or not merge._merge.eq('both').all():
    raise RuntimeError('Error correspondencia OA')
print('=== PASO 45: AUDITORIA IST_ORIG Y PUNTAJES ===',flush=True)
orig = pd.to_numeric(merge.original_IST_ORIG,errors='coerce')
count_na = int(orig.isna().sum())
valid = orig.between(0,100)
print(f'IST_ORIG: en [0,100]={valid.sum()}, fuera de rango={(~valid & orig.notna()).sum()}, nulos={count_na}')
print('Valores fuera de rango mas frecuentes:')
print(orig[~valid & orig.notna()].value_counts(dropna=False).head(20).to_string())
print('Resumen cuantiles IST_ORIG en rango:')
print(orig[valid].describe().to_string() if valid.any() else '(ninguno)')
print('Comparacion IST_100 original vs recalculado:')
old100 = pd.to_numeric(merge.original_IST_100,errors='coerce')
diff100 = merge.IST_100-old100
print(f' comparables={diff100.notna().sum()}, MAE={diff100.abs().mean():.12g}, max={diff100.abs().max():.12g}')
valid_delta = merge.loc[valid,'IST_100']-orig.loc[valid]
print('Comparacion IST_ORIG SOLO valores [0,100]:')
print(f' comparables={valid_delta.notna().sum()}, MAE={valid_delta.abs().mean():.4f}, max={valid_delta.abs().max():.4f}, diferencias>1={(valid_delta.abs()>1).sum()}')
rows=[]
for code in ['AP','SB','GL','HU','AI','CI','AD','PO','TU']:
    a=merge.get('S_'+code);b=merge.get('original_S_'+code)
    if a is None or b is None: continue
    aa=pd.to_numeric(a,errors='coerce');bb=pd.to_numeric(b,errors='coerce'); dif=aa-bb
    rows.append({'componente':code,'n_comparables':int(dif.notna().sum()),'n_distintos_gt_1e_6':int((dif.abs()>1e-6).sum()),'mae_puntaje':dif.abs().mean(),'max_diferencia':dif.abs().max()})
comps=pd.DataFrame(rows)
print('Comparacion puntajes originales/recalculados:')
print(comps.to_string(index=False))
comps.to_csv(OUT/'45_validacion_componentes.csv',index=False,encoding='utf-8-sig')
merge['IST_ORIG_numerico']=orig
merge['IST_ORIG_rango_valido_0_100']=valid
merge['diferencia_IST_ORIG_si_valido']=np.where(valid, merge.IST_100-orig,np.nan)
merge['diferencia_IST_100']=diff100
merge.to_csv(OUT/'45_auditoria_ist_orig.csv',index=False,encoding='utf-8-sig')
print('Reportes: 45_auditoria_ist_orig.csv; 45_validacion_componentes.csv')
print('PASO 45 FINALIZADO',flush=True)
