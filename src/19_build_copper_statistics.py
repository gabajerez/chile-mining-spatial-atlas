from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "outputs" / "tables"
TABLES.mkdir(parents=True, exist_ok=True)

print("=== ESTADISTICAS TERRITORIALES DEL COBRE ===", flush=True)

# Datos previamente calculados mediante union espacial
oa = pd.read_csv(
    TABLES / "oa_cobertura_comunal.csv",
    dtype={"codreg": str, "codcom": str}
)

# Matriz de las tres fuentes
mineria = pd.read_csv(
    TABLES / "matriz_mineria_comunal_v1.csv",
    dtype={"codreg": str, "codcom": str}
)

for df in (oa, mineria):
    df["codreg"] = df["codreg"].str.zfill(2)
    df["codcom"] = df["codcom"].str.zfill(5)

if oa["codcom"].duplicated().any():
    raise ValueError("Codigos duplicados en OA")

if mineria["codcom"].duplicated().any():
    raise ValueError("Codigos duplicados en matriz minera")

cols = [
    "codcom", "cobre_exclusivo_ha",
    "cobre_asociado_ha", "sin_cobre_ha",
    "cobre_total_ha"
]

df = mineria.drop(
    columns=[
        "cobre_exclusivo_ha",
        "cobre_asociado_ha",
        "sin_cobre_ha",
        "cobre_total_ha"
    ],
    errors="ignore"
).merge(
    oa[cols],
    on="codcom",
    how="left",
    validate="one_to_one"
)

if len(df) != 343:
    raise ValueError("Numero inesperado de comunas")

if df[cols[1:]].isna().any().any():
    raise ValueError("Faltan superficies de cobre")

# Indicadores territoriales
area = df["superficie_comunal_ha"]

df["cobre_pct_comunal"] = (
    df["cobre_total_ha"] / area * 100
)

df["cobre_pct_oa"] = np.where(
    df["oa_ha"] > 0,
    df["cobre_total_ha"] / df["oa_ha"] * 100,
    np.nan
)

df["cobre_exclusivo_pct_comunal"] = (
    df["cobre_exclusivo_ha"] / area * 100
)

df["cobre_asociado_pct_comunal"] = (
    df["cobre_asociado_ha"] / area * 100
)

# Superficie compartida entre ambas clases
df["cobre_clases_overlap_ha"] = (
    df["cobre_exclusivo_ha"]
    + df["cobre_asociado_ha"]
    - df["cobre_total_ha"]
)

# Controles de integridad
tol = 0.05

if (df["cobre_total_ha"] > df["oa_ha"] + tol).any():
    raise ValueError("Cobre excede superficie OA")

if (df["cobre_clases_overlap_ha"] < -tol).any():
    raise ValueError("Balance incorrecto entre clases de cobre")

if (df["cobre_pct_comunal"] > 100.000001).any():
    raise ValueError("Cobertura de cobre superior al 100%")

if df["cochilco_cobre_n"].sum() != 40:
    raise ValueError("Conteo COCHILCO cobre inesperado")

# Ordenar y guardar
df = df.sort_values(["codreg", "codcom"])

df.to_csv(
    TABLES / "matriz_cobre_comunal_v1.csv",
    index=False,
    encoding="utf-8-sig"
)

# Agregacion regional
regional_cols = [
    "superficie_comunal_ha",
    "oa_ha",
    "cobre_exclusivo_ha",
    "cobre_asociado_ha",
    "cobre_total_ha",
    "cobre_clases_overlap_ha",
    "cochilco_n",
    "cochilco_cobre_n"
]

reg = (
    df.groupby(["codreg", "nomreg"], as_index=False)
    [regional_cols].sum()
)

reg["cobre_pct_regional"] = (
    reg["cobre_total_ha"] /
    reg["superficie_comunal_ha"] * 100
)

reg["cobre_pct_oa"] = np.where(
    reg["oa_ha"] > 0,
    reg["cobre_total_ha"] / reg["oa_ha"] * 100,
    np.nan
)

reg = reg.sort_values("cobre_total_ha", ascending=False)

if len(reg) != 16:
    raise ValueError("Numero inesperado de regiones")

reg.to_csv(
    TABLES / "matriz_cobre_regional_v1.csv",
    index=False,
    encoding="utf-8-sig"
)

# Resumen nacional
oa_total = float(df["oa_ha"].sum())
cobre_total = float(df["cobre_total_ha"].sum())
territorio = float(area.sum())

print("\n=== RESULTADOS NACIONALES ===")
print("Comunas:", len(df))
print("Regiones:", len(reg))
print("Superficie OA (ha):", round(oa_total, 2))
print("Cobre total (ha):", round(cobre_total, 2))
print(
    "Cobre como porcentaje de OA:",
    round(cobre_total / oa_total * 100, 3)
)
print(
    "Cobertura territorial cobre (%):",
    round(cobre_total / territorio * 100, 4)
)
print(
    "Comunas con cobre OA:",
    int((df["cobre_total_ha"] > 0).sum())
)
print(
    "Proyectos COCHILCO cobre:",
    int(df["cochilco_cobre_n"].sum())
)

print("\n=== REGIONES CON MAYOR SUPERFICIE DE COBRE ===")
print(
    reg[[
        "nomreg",
        "cobre_total_ha",
        "cobre_pct_regional",
        "cobre_pct_oa",
        "cochilco_cobre_n"
    ]].head(10).to_string(index=False)
)

print("\n=== TOP 15 COMUNAS POR SUPERFICIE DE COBRE ===")
print(
    df.sort_values("cobre_total_ha", ascending=False)[[
        "nomreg", "nomcom",
        "cobre_total_ha",
        "cobre_pct_comunal",
        "cochilco_cobre_n"
    ]].head(15).to_string(index=False)
)

print("\nARCHIVOS GENERADOS:")
print("matriz_cobre_comunal_v1.csv")
print("matriz_cobre_regional_v1.csv")
print("\nPROCESO FINALIZADO", flush=True)
