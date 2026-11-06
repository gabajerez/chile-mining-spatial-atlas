from pathlib import Path
import re
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "enmc"
OUT.mkdir(parents=True, exist_ok=True)

oa = pd.read_csv(
    OUT / "25_oa_enmc_revision.csv",
    encoding="utf-8-sig",
    low_memory=False
)

co = pd.read_csv(
    OUT / "25_cochilco_enmc_revision.csv",
    encoding="utf-8-sig",
    low_memory=False
)

oa_objects = set(
    oa["OBJECTID"].dropna().astype(int)
)

def parse_ids(value):
    if pd.isna(value):
        return []
    return [
        int(x) for x in re.findall(
            r"\d+", str(value)
        )
    ]

rows = []

for _, p in co.iterrows():
    ids = parse_ids(p["oa_objid"])

    matched = [
        i for i in ids if i in oa_objects
    ]
    unmatched = [
        i for i in ids if i not in oa_objects
    ]

    has_oa = len(ids) > 0

    # Ningún proyecto se clasifica automáticamente
    # como superficie nueva.
    if has_oa:
        priority = (
            "Verificar huella nueva fuera de OA"
        )
    else:
        priority = (
            "Prioritario: buscar geometria de proyecto"
        )

    rows.append({
        "fila_xls": p["fila_xls"],
        "proyecto": p["proyecto"],
        "mineral_original": p["Mineral"],
        "minerales_enmc": p["minerales_enmc"],
        "region": p["region"],
        "tipo_proyecto": p["tipo_proy"],
        "etapa": p["etapa"],
        "condicion": p["condicion"],
        "oa_estado_original": p["oa_estado"],
        "oa_objid": p["oa_objid"],
        "n_geometrias_oa_referidas": len(ids),
        "n_oa_dentro_filtro_enmc": len(matched),
        "oa_ids_fuera_filtro_enmc": "; ".join(
            str(i) for i in unmatched
        ),
        "prioridad_revision": priority,
        "nueva_superficie_acreditada": "PENDIENTE",
        "fuente_poligono_nuevo": "",
        "observaciones_validacion": ""
    })

result = pd.DataFrame(rows)

if len(result) != 55:
    raise RuntimeError(
        f"Se esperaban 55 proyectos: {len(result)}"
    )

result = result.sort_values(
    ["n_geometrias_oa_referidas",
     "tipo_proyecto", "proyecto"]
)

dest = OUT / "26_matriz_revision_proyectos_enmc.csv"

result.to_csv(
    dest,
    index=False,
    encoding="utf-8-sig"
)

print("=== MATRIZ PROYECTOS ENMC ===")
print("Total proyectos:", len(result))

print(
    "Sin OA:",
    int((result["n_geometrias_oa_referidas"] == 0).sum())
)

print(
    "Con OA:",
    int((result["n_geometrias_oa_referidas"] > 0).sum())
)

print(
    "Proyectos con referencias fuera del filtro ENMC:",
    int(
        (result["oa_ids_fuera_filtro_enmc"] != "").sum()
    )
)

print("\nProyectos prioritarios:")
print(
    result.loc[
        result["n_geometrias_oa_referidas"] == 0,
        ["proyecto", "mineral_original",
         "tipo_proyecto"]
    ].to_string(index=False)
)

print("\nArchivo generado:", dest)
print("PASO 26 FINALIZADO")
