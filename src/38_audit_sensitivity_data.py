from pathlib import Path
import pandas as pd
import pyogrio
import zipfile
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/raw/sensibilidad"
OUT = ROOT / "reports/enmc"
OUT.mkdir(parents=True, exist_ok=True)

EXTS = {".shp", ".gpkg", ".geojson", ".kml", ".fgb"}
records = []

def normalize(value):
    txt = unicodedata.normalize("NFKD", str(value).lower())
    return "".join(c for c in txt if not unicodedata.combining(c))

def identify(path):
    text = normalize(str(path.relative_to(BASE)))
    rules = {
        "areas_protegidas": ["areas protegidas"],
        "sitios_prioritarios": ["sitios prioritarios"],
        "reservas_biosfera": ["reserva de la biosfera"],
        "glaciares": ["glaciares"],
        "humedales": ["inventario de humedales"],
        "planes_atmosfericos": ["planes de descontaminacion"],
        "comunidades_indigenas": ["comunidades indigenas"],
        "areas_desarrollo_indigena": ["areas de desarrollo indigena"],
        "areas_pobladas": ["areas pobladas"],
        "atractivos_turisticos": ["atractivo turistico"],
        "zonas_interes_turistico": ["zona de interes turistico"],
    }
    for category, words in rules.items():
        if any(w in text for w in words):
            return category
    return "SIN_CLASIFICAR"

def inspect(path, layer=None):
    category = identify(path)

    try:
        info = pyogrio.read_info(path, layer=layer)

        records.append({
            "categoria": category,
            "archivo": str(path.relative_to(BASE)),
            "capa": layer or path.stem,
            "formato": path.suffix.lower(),
            "registros": info.get("features"),
            "geometria": info.get("geometry_type"),
            "crs": str(info.get("crs")),
            "campos": "; ".join(map(str, info.get("fields", []))),
            "estado": "OK"
        })

    except Exception as exc:
        records.append({
            "categoria": category,
            "archivo": str(path.relative_to(BASE)),
            "capa": layer or path.stem,
            "formato": path.suffix.lower(),
            "registros": None,
            "geometria": "",
            "crs": "",
            "campos": "",
            "estado": f"ERROR: {str(exc)[:200]}"
        })

print("=== PASO 38: AUDITORIA SENSIBILIDAD ===", flush=True)

if not BASE.exists():
    raise FileNotFoundError(BASE)

# Geodatabases: tratarlas como un único conjunto
gdbs = sorted(
    p for p in BASE.rglob("*")
    if p.is_dir() and p.suffix.lower() == ".gdb"
)

for gdb in gdbs:
    try:
        for layer, _ in pyogrio.list_layers(gdb):
            inspect(gdb, layer=str(layer))
    except Exception as exc:
        print("ERROR GDB:", gdb, exc)

# Archivos individuales, excluyendo contenidos internos de GDB
for path in sorted(BASE.rglob("*")):
    if not path.is_file():
        continue

    if any(parent.suffix.lower() == ".gdb" for parent in path.parents):
        continue

    if path.suffix.lower() in EXTS:
        if path.suffix.lower() == ".gpkg":
            try:
                layers = pyogrio.list_layers(path)
                for layer, _ in layers:
                    inspect(path, layer=str(layer))
            except Exception:
                inspect(path)
        else:
            inspect(path)

    elif path.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.namelist()
                spatial = [
                    name for name in entries
                    if Path(name).suffix.lower() in EXTS
                ]
                print(
                    "ZIP:", path.relative_to(BASE),
                    "| archivos espaciales:", len(spatial)
                )
        except Exception as exc:
            print("ERROR ZIP:", path, exc)

df = pd.DataFrame(records, columns=[
    "categoria", "archivo", "capa", "formato",
    "registros", "geometria", "crs", "campos", "estado"
])

dest = OUT / "38_inventario_sensibilidad.csv"
df.to_csv(dest, index=False, encoding="utf-8-sig")

print("\n=== RESUMEN POR CATEGORIA ===")

if not df.empty:
    summary = (
        df.groupby(["categoria", "geometria", "crs", "estado"],
                   dropna=False)
        .agg(
            capas=("archivo", "count"),
            entidades=("registros", "sum")
        )
        .reset_index()
    )

    print(summary.to_string(index=False))
else:
    print("No se detectaron capas legibles.")

print("\nArchivo:", dest)
print("PASO 38 FINALIZADO")
