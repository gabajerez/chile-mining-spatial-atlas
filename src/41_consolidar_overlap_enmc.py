"""Consolida los resultados del paso 40 sin sumar geometrías entre categorías.
Ejecutar desde cualquier directorio: python src/41_consolidar_overlap_enmc.py
"""
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports' / 'enmc'
REPORT.mkdir(parents=True, exist_ok=True)

COMPONENTES = [
    'areas_protegidas', 'sitios_prioritarios', 'reservas_biosfera',
    'glaciares', 'humedales', 'planes_atmosfericos',
    'areas_desarrollo_indigena', 'areas_pobladas', 'zonas_interes_turistico'
]
FIELDS = [
    'componente', 'n_elementos_originales', 'superficie_sensible_unica_ha',
    'superficie_sensible_concesionada_ha', 'porcentaje_sensible_concesionada',
    'superficie_sensible_residual_provisional_ha',
    'porcentaje_sensible_residual_provisional', 'estado'
]
rows = []
for comp in COMPONENTES:
    path = REPORT / f'40_overlap_{comp}.csv'
    if not path.exists():
        raise FileNotFoundError(f'Falta el resultado de {comp}: {path}')
    df = pd.read_csv(path, encoding='utf-8-sig')
    if len(df) != 1:
        raise ValueError(f'{comp}: se esperaba una fila, hay {len(df)}')
    if not set(FIELDS).issubset(df.columns):
        raise ValueError(f'{comp}: faltan campos {set(FIELDS) - set(df.columns)}')
    row = df.loc[0, FIELDS].copy()
    if row['componente'] != comp:
        raise ValueError(f'{comp}: identificador inesperado {row["componente"]}')
    rows.append(row)

out = pd.DataFrame(rows)
for fld in FIELDS[1:7]:
    out[fld] = pd.to_numeric(out[fld], errors='raise')

for _, r in out.iterrows():
    a = r['superficie_sensible_unica_ha']
    c = r['superficie_sensible_concesionada_ha']
    l = r['superficie_sensible_residual_provisional_ha']
    if not (np.isfinite(a) and a > 0 and -0.01 <= l <= c + 0.01 and c <= a + 0.01):
        raise ValueError(f'Balance de superficies inválido: {r["componente"]}')
    if not np.isclose(c/a*100, r['porcentaje_sensible_concesionada'], atol=0.005):
        raise ValueError(f'Porcentaje constituido inconsistente: {r["componente"]}')
    if not np.isclose(l/a*100, r['porcentaje_sensible_residual_provisional'], atol=0.005):
        raise ValueError(f'Porcentaje residual inconsistente: {r["componente"]}')

out = out.sort_values('porcentaje_sensible_concesionada', ascending=False)
out.to_csv(REPORT / '41_matriz_overlap_enmc.csv', index=False, encoding='utf-8-sig')

labels = {
    'areas_protegidas':'Áreas protegidas', 'sitios_prioritarios':'Sitios prioritarios',
    'reservas_biosfera':'Reservas de biosfera', 'glaciares':'Glaciares',
    'humedales':'Humedales', 'planes_atmosfericos':'Planes atmosféricos',
    'areas_desarrollo_indigena':'Áreas de desarrollo indígena',
    'areas_pobladas':'Áreas pobladas', 'zonas_interes_turistico':'Zonas de interés turístico'
}
lines = [
    '# Superposición concesional con capas sensibles — resultados provisionales', '',
    'Cobertura de concesiones constituidas y residual provisional sobre la superficie única de cada capa.',
    'Las categorías pueden superponerse entre sí: **no sumar hectáreas entre filas**.',
    'El residual descuenta polígonos OA candidatos y **no** descuenta polígonos nuevos COCHILCO.', '',
    '| Capa | Área sensible (ha) | Área concesionada (ha) | Constituida (%) | Residual provisional (%) |',
    '|---|---:|---:|---:|---:|'
]
for _, r in out.iterrows():
    fmt = lambda v, decimals=2: f'{v:,.{decimals}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    lines.append(f'| {labels[r["componente"]]} | {fmt(r["superficie_sensible_unica_ha"])} | {fmt(r["superficie_sensible_concesionada_ha"])} | {fmt(r["porcentaje_sensible_concesionada"])} | {fmt(r["porcentaje_sensible_residual_provisional"])} |')
lines.extend([
    '', '## Limitaciones',
    '- Porcentajes referidos a la geometría disponible y al ámbito de las 343 comunas.',
    '- Las coincidencias espaciales no equivalen a impactos ambientales.',
    '- Los resultados requieren revisión de cobertura y categoría de cada fuente cartográfica.',
    '- Sitios prioritarios y reservas de biosfera requieren unión conjunta para el componente IST; lo mismo ocurre con atractivos y zonas turísticas.',
    '- Comunidades indígenas y atractivos turísticos están representados por puntos; se evaluarán mediante proximidad.',
    '- El cálculo final de concesión latente depende de la validación de las operaciones OA y de nuevas huellas COCHILCO.'
])
(REPORT / '41_resumen_overlap_enmc.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
print('=== PASO 41: CONSOLIDACION ===')
print(out[['componente','porcentaje_sensible_concesionada','porcentaje_sensible_residual_provisional']].to_string(index=False))
print('Generados: 41_matriz_overlap_enmc.csv; 41_resumen_overlap_enmc.md')
print('PASO 41 FINALIZADO')
