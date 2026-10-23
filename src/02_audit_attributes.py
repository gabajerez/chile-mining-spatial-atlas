from pathlib import Path
import pandas as pd
import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports"
OUT.mkdir(parents=True, exist_ok=True)

LAYERS = {
    "OA": {
        "file": "OA-2-Articulo.shp",
        "fields": [
            "REGION", "COMUNA", "MINERAL",
            "TIPO", "TAM_EMP", "CAT_SERN"
        ],
        "ids": ["ID_OA", "ID_POL"]
    },
    "COCHILCO": {
        "file": "Cartera de proyecto COCHILCO.shp",
        "fields": [
            "region", "Mineral", "Mineral cr",
            "Nivel", "etapa", "condicion",
            "tipo_proy", "oa_estado", "oa_metodo"
        ],
        "ids": ["fila_xls", "oa_id"]
    },
    "CONCESIONES": {
        "file": "sernageomin_concesiones_2026-06-05.geojson",
        "fields": [
            "COMUNA", "TIPO_CONCESION",
            "SITUACION_CONCESION", "ORIGEN",
            "TITULAR_DIVISION"
        ],
        "ids": ["ID_CONCESION", "NUMERO_ROL"]
    }
}

all_rows = []
id_rows = []

for name, config in LAYERS.items():
    print("\n" + "=" * 70)
    print("CAPA:", name)
    print("=" * 70)

    gdf = gpd.read_file(
        ROOT / config["file"],
        engine="pyogrio",
        ignore_geometry=True
    )

    for field in config["fields"]:
        if field not in gdf.columns:
            print("CAMPO NO ENCONTRADO:", field)
            continue

        counts = (
            gdf[field]
            .fillna("<NULO>")
            .astype(str)
            .value_counts(dropna=False)
        )

        print(f"\n{field}: {len(counts)} categorias")
        print(counts.head(20).to_string())

        for value, count in counts.items():
            all_rows.append({
                "capa": name,
                "campo": field,
                "valor": value,
                "cantidad": int(count)
            })

    for field in config["ids"]:
        if field not in gdf.columns:
            continue

        serie = gdf[field]
        valid = serie.dropna()

        id_rows.append({
            "capa": name,
            "campo_id": field,
            "registros": len(gdf),
            "nulos": int(serie.isna().sum()),
            "valores_unicos": int(valid.nunique()),
            "registros_duplicados": int(
                valid.duplicated(keep=False).sum()
            )
        })

pd.DataFrame(all_rows).to_csv(
    OUT / "audit_attribute_categories.csv",
    index=False,
    encoding="utf-8-sig"
)

pd.DataFrame(id_rows).to_csv(
    OUT / "audit_identifiers.csv",
    index=False,
    encoding="utf-8-sig"
)

print("\n" + "=" * 70)
print("RESUMEN IDENTIFICADORES")
print("=" * 70)
print(pd.DataFrame(id_rows).to_string(index=False))

print("\nARCHIVOS GENERADOS:")
print(OUT / "audit_attribute_categories.csv")
print(OUT / "audit_identifiers.csv")
