from pathlib import Path
import re
import unicodedata
import pandas as pd
import pyogrio

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "enmc"
OUT.mkdir(parents=True, exist_ok=True)

SEARCH_DIRS = [
    ROOT / "data",
    ROOT / "insumos",
    ROOT / "capas",
]

EXTENSIONS = {
    ".gpkg", ".shp", ".geojson",
    ".json", ".kml", ".kmz", ".fgb"
}

KEYWORDS = {
    "areas_protegidas": [
        "proteg", "snbp", "simbio",
        "parque", "reserva", "santuario"
    ],
    "glaciares": [
        "glaciar", "hielo"
    ],
    "humedales": [
        "humedal", "wetland", "turbera"
    ],
    "territorios_indigenas": [
        "indigena", "conadi",
        "titulo_merced", "tierra_indigena"
    ],
    "sitios_prioritarios": [
        "sitio_prioritario", "prioritario",
        "biodiversidad"
    ],
    "salares_litio": [
        "salar", "litio", "ceol", "salmuera"
    ]
}

def norm(value):
    value = unicodedata.normalize(
        "NFKD", str(value).lower()
    )
    return "".join(
        c for c in value
        if not unicodedata.combining(c)
    )

def identify(text):
    text = norm(text)
    return "; ".join(
        category for category, words in KEYWORDS.items()
        if any(word in text for word in words)
    )

records = []

for folder in SEARCH_DIRS:
    if not folder.exists():
        continue

    for path in folder.rglob("*"):
        if not path.is_file():
            continue

        if path.suffix.lower() not in EXTENSIONS:
            continue

        # JSON genéricos pueden ser configuraciones
        if path.suffix.lower() == ".json":
            if not identify(path.name):
                continue

        layers = [(path.stem, None)]

        if path.suffix.lower() == ".gpkg":
            try:
                layers = [
                    (str(item[0]), str(item[1]))
                    for item in pyogrio.list_layers(path)
                ]
            except Exception as exc:
                layers = [
                    (path.stem, f"ERROR: {exc}")
                ]

        for layer, geometry_type in layers:
            category = identify(
                f"{path.name} {layer}"
            )

            records.append({
                "archivo": str(path.relative_to(ROOT)),
                "capa": layer,
                "tipo_geometria": geometry_type or "",
                "categoria_candidata": category,
                "tamano_mb": round(
                    path.stat().st_size / 1048576, 2
                )
            })

df = pd.DataFrame(
    records,
    columns=[
        "archivo", "capa", "tipo_geometria",
        "categoria_candidata", "tamano_mb"
    ]
)

df = df.sort_values(
    ["categoria_candidata", "archivo", "capa"]
)

df.to_csv(
    OUT / "36_inventario_geoespacial.csv",
    index=False,
    encoding="utf-8-sig"
)

sensitive = df[
    df["categoria_candidata"] != ""
].copy()

sensitive.to_csv(
    OUT / "36_capas_sensibles_candidatas.csv",
    index=False,
    encoding="utf-8-sig"
)

print("=== PASO 36: INVENTARIO TERRITORIAL ===")
print("Archivos/capas detectados:", len(df))
print("Candidatos a sensibilidad:", len(sensitive))

if not sensitive.empty:
    print("\nCAPAS CANDIDATAS:")
    print(
        sensitive[
            ["archivo", "capa", "categoria_candidata"]
        ].to_string(index=False)
    )

print("\nDOCUMENTOS METODOLOGICOS CANDIDATOS:")

patterns = [
    "sensibilidad", "metodologia",
    "ponderacion", "indice_territorial",
    "ist_", "documento_trabajo"
]

for folder in [ROOT / "reports", ROOT / "docs", ROOT / "src"]:
    if not folder.exists():
        continue

    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {
            ".py", ".md", ".txt", ".pdf", ".docx"
        }:
            continue
        if any(p in norm(path.name) for p in patterns):
            print(" -", path.relative_to(ROOT))

print("\nPASO 36 FINALIZADO")
