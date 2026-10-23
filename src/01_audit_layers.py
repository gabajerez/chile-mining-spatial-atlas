from pathlib import Path
import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

LAYERS = {
    "OA": "OA-2-Articulo.shp",
    "COCHILCO": "Cartera de proyecto COCHILCO.shp",
    "CONCESIONES": "sernageomin_concesiones_2026-06-05.geojson",
}

results = []

for name, filename in LAYERS.items():
    print("\n" + "=" * 70)
    print("CAPA:", name)
    print("=" * 70)

    path = ROOT / filename

    if not path.exists():
        print("ARCHIVO NO ENCONTRADO:", path)
        continue

    try:
        gdf = gpd.read_file(path, engine="pyogrio")

        print("Registros:", len(gdf))
        print("CRS:", gdf.crs)
        print("Tipos de geometria:")
        print(gdf.geom_type.value_counts().to_string())

        print("\nCOLUMNAS:")
        print(gdf.dtypes.to_string())

        print("\nPRIMEROS 3 REGISTROS:")
        print(
            gdf.drop(columns=gdf.geometry.name)
            .head(3)
            .to_string(index=False, max_cols=20)
        )

        print("\nCALIDAD GEOMETRICA:")
        print("Nulas:", gdf.geometry.isna().sum())
        print("Vacias:", gdf.geometry.is_empty.sum())
        print("Invalidas:", (~gdf.geometry.is_valid).sum())
        print("Extension:", gdf.total_bounds)

        results.append({
            "capa": name,
            "registros": len(gdf),
            "crs": str(gdf.crs),
            "nulas": int(gdf.geometry.isna().sum()),
            "invalidas": int((~gdf.geometry.is_valid).sum())
        })

    except Exception as e:
        print("ERROR:", str(e))

output = ROOT / "reports" / "audit_layers.csv"
output.parent.mkdir(parents=True, exist_ok=True)

pd.DataFrame(results).to_csv(
    output,
    index=False,
    encoding="utf-8-sig"
)

print("\nAUDITORIA FINALIZADA")
print("Reporte:", output)
