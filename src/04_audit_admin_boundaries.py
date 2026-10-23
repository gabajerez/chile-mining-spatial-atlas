from pathlib import Path
import geopandas as gpd

root = Path("data/external")
files = list(root.rglob("*.shp"))

if not files:
    print("No se encontraron shapefiles.")
    raise SystemExit(1)

for path in files:
    print("\n" + "=" * 65)
    print("ARCHIVO:", path)
    print("=" * 65)

    try:
        gdf = gpd.read_file(path, engine="pyogrio")

        print("Registros:", len(gdf))
        print("CRS:", gdf.crs)
        print("Columnas:", list(gdf.columns))
        print("Geometrias:", gdf.geom_type.value_counts().to_dict())
        print("Invalidas:", int((~gdf.geometry.is_valid).sum()))
        print("Extension:", gdf.total_bounds.tolist())

        print("\nPrimeros registros:")
        print(
            gdf.drop(columns=gdf.geometry.name)
            .head(5)
            .to_string(index=False)
        )

    except Exception as exc:
        print("ERROR:", str(exc))
