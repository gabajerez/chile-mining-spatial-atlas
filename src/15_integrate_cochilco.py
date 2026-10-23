from pathlib import Path
import pandas as pd
import geopandas as gpd
import shapely
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed"
OUT = ROOT / "outputs/tables"
OUT.mkdir(parents=True, exist_ok=True)

def norm(value):
    if pd.isna(value):
        return ""
    text = unicodedata.normalize(
        "NFKD", str(value).strip().upper()
    )
    return "".join(
        c for c in text if not unicodedata.combining(c)
    )

print("=== INTEGRACION COCHILCO ===", flush=True)

co = gpd.read_file(
    ROOT / "Cartera de proyecto COCHILCO.shp",
    engine="pyogrio"
)

oa = gpd.read_file(
    ROOT / "OA-2-Articulo.shp",
    engine="pyogrio"
)

con = gpd.read_file(
    DATA / "concesiones_final_6933.gpkg",
    columns=["ID_CONCESION", "SITUACION_CONCESION"],
    engine="pyogrio"
)

com = gpd.read_file(
    DATA / "comunas_consolidadas.gpkg",
    engine="pyogrio"
)

if len(co) != 57:
    raise ValueError("Cantidad COCHILCO inesperada")

def fix_polygon(geom):
    if geom is None or geom.is_empty:
        return shapely.GeometryCollection()
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
    parts = [
        p for p in shapely.get_parts(geom)
        if p.geom_type in ("Polygon", "MultiPolygon")
    ]
    return shapely.union_all(parts) if parts else shapely.GeometryCollection()

oa["geometry"] = oa.geometry.map(fix_polygon)

co = co.to_crs(6933)
oa = oa.to_crs(6933)
con = con.to_crs(6933)
com = com.to_crs(6933)

con = con.loc[
    con["SITUACION_CONCESION"] == "CONSTITUIDA"
].copy()

for col in ["codcom", "codreg"]:
    com[col] = (
        com[col].astype(str)
        .str.zfill(5 if col == "codcom" else 2)
    )

idx_com = com.sindex
idx_oa = oa.sindex
idx_con = con.sindex

rows = []

for _, project in co.iterrows():
    point = project.geometry

    if point is None or point.is_empty:
        raise ValueError("Proyecto sin geometria")

    matches_com = idx_com.query(
        point, predicate="intersects"
    )

    matches_oa = idx_oa.query(
        point, predicate="intersects"
    )

    matches_con = idx_con.query(
        point, predicate="intersects"
    )

    # Un punto en frontera puede coincidir con mas de una comuna
    admin = com.iloc[matches_com].copy()

    if len(admin) == 1:
        codcom = admin.iloc[0]["codcom"]
        codreg = admin.iloc[0]["codreg"]
        nomcom = admin.iloc[0]["nomcom"]
        nomreg = admin.iloc[0]["nomreg"]
        estado_admin = "UNICA"
    else:
        codcom = ""
        codreg = ""
        nomcom = ""
        nomreg = ""
        estado_admin = (
            "SIN_COMUNA" if len(admin) == 0
            else "FRONTERA_MULTIPLE"
        )

    mineral = norm(project.get("Mineral"))
    cobre = mineral == "COBRE" or "COBRE" in mineral.split()

    critico = norm(project.get("Mineral cr"))

    rows.append({
        "fila_xls": project["fila_xls"],
        "proyecto": project.get("proyecto"),
        "empresa": project.get("empresa"),
        "mineral": project.get("Mineral"),
        "mineral_critico_original": project.get("Mineral cr"),
        "region_fuente": project.get("region"),
        "codreg": codreg,
        "codcom": codcom,
        "nomreg": nomreg,
        "nomcom": nomcom,
        "estado_asignacion": estado_admin,
        "n_comunas_coincidentes": len(admin),
        "cobre": int(cobre),
        "critico_si": int(critico == "SI"),
        "critico_no_informado": int(critico == ""),
        "en_oa": int(len(matches_oa) > 0),
        "en_concesion": int(len(matches_con) > 0),
        "en_ambas": int(
            len(matches_oa) > 0 and len(matches_con) > 0
        ),
        "n_poligonos_oa": len(matches_oa),
        "n_concesiones": len(matches_con),
        "oa_estado_fuente": project.get("oa_estado"),
        "oa_id_fuente": project.get("oa_id")
    })

df = pd.DataFrame(rows)

df.to_csv(
    OUT / "cochilco_integracion_proyectos.csv",
    index=False,
    encoding="utf-8-sig"
)

print("\n=== CONTROL DE ASIGNACION ===")
print(df["estado_asignacion"].value_counts().to_string())
print("Proyectos:", len(df))
print("En OA:", int(df["en_oa"].sum()))
print("En concesion:", int(df["en_concesion"].sum()))
print("En ambas:", int(df["en_ambas"].sum()))
print("Cobre:", int(df["cobre"].sum()))

# Solo asignaciones administrativas unicas
valid = df.loc[
    df["estado_asignacion"] == "UNICA"
].copy()

metrics = {
    "cochilco_n": ("fila_xls", "nunique"),
    "cochilco_cobre_n": ("cobre", "sum"),
    "cochilco_critico_si_n": ("critico_si", "sum"),
    "cochilco_critico_no_informado_n":
        ("critico_no_informado", "sum"),
    "cochilco_en_oa_n": ("en_oa", "sum"),
    "cochilco_en_concesion_n": ("en_concesion", "sum"),
    "cochilco_en_ambas_n": ("en_ambas", "sum")
}

by_com = valid.groupby("codcom").agg(**metrics)
by_reg = valid.groupby("codreg").agg(**metrics)

base_com = pd.read_csv(
    OUT / "integracion_oa_concesiones_comunal.csv",
    dtype={"codcom": str, "codreg": str}
)

base_reg = pd.read_csv(
    OUT / "integracion_oa_concesiones_regional.csv",
    dtype={"codreg": str}
)

base_com["codcom"] = base_com["codcom"].str.zfill(5)
base_reg["codreg"] = base_reg["codreg"].str.zfill(2)

final_com = base_com.merge(
    by_com, left_on="codcom", right_index=True, how="left"
)

final_reg = base_reg.merge(
    by_reg, left_on="codreg", right_index=True, how="left"
)

for frame in [final_com, final_reg]:
    for col in metrics:
        frame[col] = frame[col].fillna(0).astype(int)

if len(final_com) != 343 or len(final_reg) != 16:
    raise ValueError("Perdida de unidades administrativas")

if df["fila_xls"].nunique() != 57:
    raise ValueError("Identificadores COCHILCO duplicados")

if valid["fila_xls"].nunique() != len(valid):
    raise ValueError("Asignaciones duplicadas")

if final_com["cochilco_n"].sum() != len(valid):
    raise ValueError("Conteo comunal inconsistente")

if final_reg["cochilco_n"].sum() != len(valid):
    raise ValueError("Conteo regional inconsistente")

final_com.to_csv(
    OUT / "matriz_mineria_comunal_v1.csv",
    index=False,
    encoding="utf-8-sig"
)

final_reg.to_csv(
    OUT / "matriz_mineria_regional_v1.csv",
    index=False,
    encoding="utf-8-sig"
)

print("\n=== RESUMEN POR REGION ===")
print(
    final_reg[[
        "nomreg", "union_total_pct",
        "cochilco_n", "cochilco_cobre_n",
        "cochilco_en_oa_n",
        "cochilco_en_concesion_n"
    ]].sort_values(
        "cochilco_n", ascending=False
    ).to_string(index=False)
)

print("\nArchivos generados:")
print("cochilco_integracion_proyectos.csv")
print("matriz_mineria_comunal_v1.csv")
print("matriz_mineria_regional_v1.csv")
print("\nINTEGRACION FINALIZADA", flush=True)
