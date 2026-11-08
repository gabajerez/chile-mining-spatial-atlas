from pathlib import Path
import geopandas as gpd
import shapely
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data/processed"
OUT = ROOT / "reports/enmc"
OUT.mkdir(parents=True, exist_ok=True)

CRS = "EPSG:6933"

CON = PROC / "enmc/32_union_concesiones_constituidas.gpkg"
COM = PROC / "comunas_consolidadas.gpkg"

OLD_HA = 16239453.73

print("=== PASO 34: CONCILIACION TERRITORIAL ===", flush=True)

def polygonal(g):
    if not g.is_valid:
        g = shapely.make_valid(g)
    if g.geom_type in ("Polygon", "MultiPolygon"):
        return g
    parts = [
        p for p in shapely.get_parts(g)
        if p.geom_type in ("Polygon", "MultiPolygon")
    ]
    return shapely.union_all(parts) if parts else shapely.GeometryCollection()

def area_ha(g):
    return g.area / 10000.0

# Unión ya procesada
con = gpd.read_file(CON, engine="pyogrio").to_crs(CRS)
assert len(con) == 1, "Se esperaba una unión concesional"

C = polygonal(con.geometry.iloc[0])

# Unión de límites administrativos
com = gpd.read_file(COM, engine="pyogrio").to_crs(CRS)

print("Comunas:", len(com), flush=True)

geoms = [
    polygonal(g)
    for g in com.geometry
    if g is not None and not g.is_empty
]

T = polygonal(shapely.union_all(geoms))

# Separar cobertura dentro y fuera de comunas
inside = polygonal(C.intersection(T))
outside = polygonal(C.difference(T))

total_ha = area_ha(C)
inside_ha = area_ha(inside)
outside_ha = area_ha(outside)

balance_error = total_ha - inside_ha - outside_ha
old_difference = total_ha - OLD_HA
inside_difference = inside_ha - OLD_HA

rows = [
    ("concesiones_union_nacional_ha", total_ha),
    ("concesiones_dentro_comunas_ha", inside_ha),
    ("concesiones_fuera_comunas_ha", outside_ha),
    ("atlas_original_ha", OLD_HA),
    ("diferencia_nacional_original_ha", old_difference),
    ("diferencia_recortada_original_ha", inside_difference),
    ("error_balance_ha", balance_error),
    ("pct_fuera_comunas", outside_ha / total_ha * 100),
]

df = pd.DataFrame(rows, columns=["indicador", "valor"])

dest = OUT / "34_conciliacion_cobertura_concesional.csv"
df.to_csv(dest, index=False, encoding="utf-8-sig")

print("\n=== RESULTADOS ===")
print(df.to_string(index=False))

if abs(balance_error) > 0.01:
    raise RuntimeError("No cierra el balance geométrico")

if abs(inside_difference) < 1.0:
    print(
        "\nDIAGNOSTICO: la diferencia se explica "
        "por superficie fuera de las comunas."
    )
else:
    print(
        "\nDIAGNOSTICO: persisten diferencias "
        "dentro del territorio comunal."
    )
    print(
        "Revisar metodología de agregación, "
        "límites administrativos y geometrías."
    )

print("\nArchivo:", dest)
print("PASO 34 FINALIZADO")
