from pathlib import Path
import re
import unicodedata
import pandas as pd
import geopandas as gpd
import pyogrio

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports"
OUT.mkdir(parents=True, exist_ok=True)

OA_PATH = ROOT / "OA-2-Articulo.shp"
CO_PATH = ROOT / "Cartera de proyecto COCHILCO.shp"
CON_PATH = ROOT / "data/processed/concesiones_final_6933.gpkg"

ENMC = {
    "cobre": [r"\bcobre\b", r"\bcopper\b"],
    "litio": [r"\blitio\b", r"\blithium\b"],
    "molibdeno": [r"\bmolibdeno\b", r"\bmolybdenum\b"],
    "renio": [r"\brenio\b", r"\brhenium\b"],
    "cobalto": [r"\bcobalto\b", r"\bcobalt\b"],
    "tierras_raras": [
        r"\btierras?\s+raras?\b",
        r"\btierras?\s+ra\b",
        r"\belementos?\s+de\s+tierras?\s+raras?\b",
        r"\bree\b",
    ],
    "antimonio": [r"\bantimonio\b"],
    "selenio": [r"\bselenio\b"],
    "telurio": [r"\btelurio\b"],
    "oro": [r"\boro\b"],
    "plata": [r"\bplata\b"],
    "hierro": [r"\bhierro\b"],
    "boro": [r"\bboro\b"],
    "yodo": [r"\byodo\b"],
}

def norm(value):
    if pd.isna(value):
        return ""
    value = unicodedata.normalize(
        "NFKD", str(value).lower()
    )
    value = "".join(
        c for c in value
        if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", value).strip()

def classify(value):
    text = norm(value)
    found = sorted(
        mineral
        for mineral, patterns in ENMC.items()
        if any(re.search(p, text) for p in patterns)
    )
    return found

def audit_source(name, path, mineral_column):
    print(f"\n=== {name} ===", flush=True)

    if not path.exists():
        raise FileNotFoundError(path)

    info = pyogrio.read_info(path)
    columns = list(info["fields"])
    print("Registros:", info["features"])
    print("CRS:", info["crs"])
    print("Columnas:", columns)

    if mineral_column not in columns:
        raise ValueError(
            f"No existe {mineral_column} en {name}"
        )

    # Solo atributos: no cargar geometrías
    df = gpd.read_file(
        path,
        ignore_geometry=True,
        engine="pyogrio"
    )

    df["_mineral_original"] = (
        df[mineral_column].fillna("").astype(str)
    )

    df["_enmc_list"] = df[
        "_mineral_original"
    ].map(classify)

    df["enmc_si"] = df["_enmc_list"].map(
        lambda values: len(values) > 0
    )

    df["minerales_enmc"] = df[
        "_enmc_list"
    ].map(lambda values: "; ".join(values))

    summary = (
        df.groupby(
            ["_mineral_original",
             "minerales_enmc", "enmc_si"],
            dropna=False
        )
        .size()
        .reset_index(name="n_registros")
        .sort_values(
            "n_registros", ascending=False
        )
    )

    summary.to_csv(
        OUT / f"audit_enmc_{name.lower()}_valores.csv",
        index=False,
        encoding="utf-8-sig"
    )

    # Identificadores y estado para revisión manual
    candidates = [
        "ID_OA", "ID_POL", "MINERAL", "Mineral",
        "ESTADO", "Estado", "estado",
        "SITUACION", "situacion", "STATUS",
        "proyecto", "Proyecto", "empresa",
        "fila_xls", "region", "REGION",
        "COMUNA"
    ]

    selected = [
        c for c in candidates if c in df.columns
    ]

    detail = df[selected].copy()
    detail["enmc_si"] = df["enmc_si"]
    detail["minerales_enmc"] = df["minerales_enmc"]

    detail.to_csv(
        OUT / f"audit_enmc_{name.lower()}_detalle.csv",
        index=False,
        encoding="utf-8-sig"
    )

    print(
        "Registros identificados ENMC:",
        int(df["enmc_si"].sum())
    )
    print(
        "Registros sin match ENMC:",
        int((~df["enmc_si"]).sum())
    )

    counts = {}
    for mineral in ENMC:
        counts[mineral] = int(
            df["_enmc_list"].map(
                lambda v: mineral in v
            ).sum()
        )

    print("Conteos por mineral:")
    for mineral, n in counts.items():
        print(f"  {mineral}: {n}")

    print("\nValores originales sin match:")
    print(
        summary.loc[
            ~summary["enmc_si"],
            ["_mineral_original", "n_registros"]
        ].head(35).to_string(index=False)
    )

    return {
        "fuente": name,
        "registros": len(df),
        "enmc_si": int(df["enmc_si"].sum()),
        "sin_match": int((~df["enmc_si"]).sum()),
        **counts
    }

print("=== AUDITORIA MINERALES CRITICOS ENMC ===")

oa = audit_source(
    "OA", OA_PATH, "MINERAL"
)

co = audit_source(
    "COCHILCO", CO_PATH, "Mineral"
)

print("\n=== CONCESIONES ===")

if not CON_PATH.exists():
    raise FileNotFoundError(CON_PATH)

info = pyogrio.read_info(CON_PATH)

print("Total registros:", info["features"])
print("Campos disponibles:")
for name in info["fields"]:
    print(" -", name)

# Buscar campos que podrían contener identificación mineral
potential = [
    col for col in info["fields"]
    if any(term in norm(col) for term in [
        "mineral", "sustancia",
        "litio", "recurso", "tipo"
    ])
]
print("Campos potenciales:", potential)

summary = pd.DataFrame([oa, co])
summary.to_csv(
    OUT / "audit_enmc_resumen_fuentes.csv",
    index=False,
    encoding="utf-8-sig"
)

print("\n=== CONTROL FINAL ===")
print(summary.to_string(index=False))
print("\nAUDITORIA FINALIZADA", flush=True)
