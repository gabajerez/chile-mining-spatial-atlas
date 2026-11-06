from pathlib import Path
from html import escape
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "enmc"
SOURCE = OUT / "27_fuentes_geometrias_proyectos.csv"

df = pd.read_csv(
    SOURCE,
    encoding="utf-8-sig",
    dtype=str
).fillna("")

priority = df[
    df["prioridad"].isin([
        "P1_NUEVO_SIN_OA",
        "P2_SIN_OA"
    ])
].copy()

assert len(priority) == 12, (
    f"Se esperaban 12 proyectos: {len(priority)}"
)

def url_link(value):
    url = str(value).strip()
    if not url.startswith(("https://", "http://")):
        return "Sin enlace"
    return (
        '<a href="' + escape(url, quote=True) +
        '" target="_blank" rel="noopener noreferrer">'
        'Abrir expediente</a>'
    )

rows = []

for _, p in priority.iterrows():
    rows.append({
        "Prioridad": p["prioridad"].split("_")[0],
        "Proyecto": escape(p["proyecto"]),
        "Mineral": escape(p["mineral_original"]),
        "Región": escape(p["region"]),
        "Tipo": escape(p["tipo_proyecto"]),
        "Referencia SEIA": escape(p["proy_seia"]),
        "Expediente": url_link(p["url_sea"]),
        "Observación": escape(p["obs_geo"])
    })

table = pd.DataFrame(rows).to_html(
    index=False,
    escape=False,
    classes="projects",
    border=0
)

html = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Revisión de geometrías ENMC</title>
<style>
body {
  font-family: Arial, sans-serif;
  max-width: 1500px;
  margin: 35px auto;
  padding: 0 20px;
  color: #23313b;
  background: #f8fafc;
}
h1 { font-size: 25px; }
p { line-height: 1.5; }
table {
  width: 100%;
  border-collapse: collapse;
  background: white;
  font-size: 13px;
}
th, td {
  border-bottom: 1px solid #e2e8f0;
  padding: 12px;
  text-align: left;
  vertical-align: top;
}
th {
  background: #17324d;
  color: white;
  position: sticky;
  top: 0;
}
tr:hover { background: #edf5fc; }
a { color: #145a9c; font-weight: bold; }
.note {
  background: #e9eef4;
  padding: 14px;
  margin: 20px 0;
  border-radius: 6px;
}
</style>
</head>
<body>
<h1>Proyectos ENMC — Revisión territorial prioritaria</h1>
<p>Proyectos COCHILCO sin asociación OA.
Se requiere confirmar si existe una geometría oficial
que represente una huella territorial nueva.</p>
<div class="note">
La ubicación puntual de COCHILCO no representa la
superficie de un proyecto. Una aprobación SEIA tampoco
acredita por sí sola que exista una huella territorial
nueva fuera de OA.
</div>
""" + table + """
</body>
</html>"""

html_file = OUT / "28_revision_geometrias.html"
html_file.write_text(html, encoding="utf-8")

columns = [
    "fila_xls", "proyecto", "mineral_original",
    "prioridad", "tipo_proyecto", "region",
    "url_sea", "proy_seia"
]

decisions = priority[columns].copy()

decisions["geometria_oficial_disponible"] = "PENDIENTE"
decisions["fuente_geometria"] = ""
decisions["ruta_archivo"] = ""
decisions["tipo_geometria"] = ""
decisions["huella_fuera_oa"] = "PENDIENTE"
decisions["decision"] = "PENDIENTE"
decisions["observaciones"] = ""

csv_file = OUT / "28_decisiones_geometrias.csv"
decisions.to_csv(
    csv_file, index=False, encoding="utf-8-sig"
)

print("=== REVISION GEOMETRIAS ENMC ===")
print("Proyectos prioritarios:", len(priority))
print(
    "Con URL SEIA:",
    priority["url_sea"].str.startswith(
        ("http://", "https://")
    ).sum()
)
print("HTML:", html_file)
print("Matriz de decisiones:", csv_file)
print("PASO 28 FINALIZADO")
