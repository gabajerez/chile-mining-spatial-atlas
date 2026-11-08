"""Paso 54: descarga reproducible del Inventario Nacional de Humedales (MMA/SIMBIO).

No sobrescribe insumos anteriores. Descarga objetos por OBJECTID en lotes y valida
integridad antes de promover el archivo temporal a definitivo.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import shape
from shapely import force_2d, make_valid

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://arcgis.mma.gob.cl/server/rest/services/SIMBIO/SIMBIO_HUMEDALES/FeatureServer/0"
OUT_DIR = ROOT / "data" / "raw" / "sensibilidad" / "humedales_nacional_mma"
REPORT_DIR = ROOT / "reports" / "enmc"
FINAL = OUT_DIR / "54_inventario_nacional_humedales.gpkg"
PARTIAL = OUT_DIR / "54_inventario_nacional_humedales.partial.gpkg"
LAYER = "humedales_mma"


def get_json(session, url, params, retries=5):
    for attempt in range(retries):
        try:
            response = session.get(url, params=params, timeout=(20, 180))
            response.raise_for_status()
            payload = response.json()
            if "error" in payload:
                raise RuntimeError(str(payload["error"]))
            return payload
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"Falló solicitud {url}: {exc}") from exc
            time.sleep(min(2 ** attempt, 20))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--replace", action="store_true", help="Reemplazar una descarga previa finalizada")
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 500:
        parser.error("--batch-size debe estar entre 1 y 500")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    if FINAL.exists() and not args.replace:
        raise FileExistsError(f"Existe descarga validada: {FINAL}. Use --replace solo si desea actualizarla.")
    if PARTIAL.exists():
        print("Eliminando descarga temporal incompleta de ejecución anterior", flush=True)
        PARTIAL.unlink()

    with requests.Session() as session:
        session.headers.update({"User-Agent": "MAPAS_GM-ENMC-research/1.0"})
        info = get_json(session, ENDPOINT, {"f": "json"})
        if info.get("geometryType") != "esriGeometryPolygon":
            raise RuntimeError("La fuente dejó de ser poligonal; revisar servicio")
        count_data = get_json(session, ENDPOINT + "/query", {"where": "1=1", "returnCountOnly": "true", "f": "json"})
        count = int(count_data["count"])
        ids_data = get_json(session, ENDPOINT + "/query", {"where": "1=1", "returnIdsOnly": "true", "f": "json"})
        ids = sorted(ids_data.get("objectIds") or [])
        print(f"=== PASO 54: INVENTARIO NACIONAL DE HUMEDALES ===\nServicio: {ENDPOINT}\nRegistros declarados: {count}; IDs recibidos: {len(ids)}", flush=True)
        if not ids or count != len(ids) or len(ids) != len(set(ids)):
            raise RuntimeError("IDs vacíos, repetidos o diferentes al conteo del servicio")

        downloaded = []
        invalid = 0
        for start in range(0, len(ids), args.batch_size):
            chunk = ids[start:start + args.batch_size]
            data = get_json(session, ENDPOINT + "/query", {
                "objectIds": ",".join(map(str, chunk)),
                "outFields": "*", "returnGeometry": "true",
                "outSR": 4326, "f": "geojson",
            })
            features = data.get("features")
            if not isinstance(features, list):
                raise RuntimeError(f"Respuesta no contiene features, lote {start}")
            frame = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
            if "OBJECTID" not in frame:
                raise RuntimeError("La respuesta no contiene OBJECTID")
            expected = set(chunk)
            observed = set(pd.to_numeric(frame.OBJECTID, errors="raise").astype(int))
            if expected != observed or len(frame) != len(chunk):
                raise RuntimeError(f"Lote incompleto {start}: esperado {len(chunk)}, recibido {len(frame)}")
            if frame.geometry.isna().any() or frame.geometry.is_empty.any():
                raise RuntimeError(f"Geometría vacía en lote {start}")
            invalid += int((~frame.geometry.is_valid).sum())
            frame.geometry = frame.geometry.map(lambda geom: force_2d(make_valid(geom)) if geom is not None else None)
            if not frame.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).all():
                raise RuntimeError(f"Geometría no poligonal tras reparación en lote {start}")
            frame.to_file(PARTIAL, layer=LAYER, driver="GPKG", engine="pyogrio", append=PARTIAL.exists(), index=False)
            downloaded.extend(int(x) for x in frame.OBJECTID)
            if (start // args.batch_size + 1) % 10 == 0 or start + args.batch_size >= len(ids):
                print(f"  Descargados: {len(downloaded)}/{count}", flush=True)

    test = gpd.read_file(PARTIAL, engine="pyogrio")
    if len(test) != count or set(downloaded) != set(ids) or test.OBJECTID.nunique() != count:
        raise RuntimeError("Fallo de integridad: cantidad o IDs no coinciden; no se promoverá archivo temporal")
    if test.crs is None or test.geometry.isna().any() or (~test.geometry.is_valid).any():
        raise RuntimeError("Fallo de integridad: CRS o geometrías")

    if FINAL.exists():
        FINAL.unlink()
    PARTIAL.replace(FINAL)
    meta = {
        "fuente": "MMA / SIMBIO - Inventario Nacional de Humedales",
        "url_servicio": ENDPOINT,
        "fecha_descarga_utc": datetime.now(timezone.utc).isoformat(),
        "numero_registros": count,
        "ids_unicos": int(test.OBJECTID.nunique()),
        "geometrias_invalidas_reparadas": invalid,
        "crs_salida": str(test.crs),
        "bounds_epsg4326": [float(v) for v in test.total_bounds],
        "archivo": str(FINAL.relative_to(ROOT)),
        "advertencia": "Validar cobertura por región, categorías ORDEN_1 y temporalidad antes de recalcular el IST",
    }
    report = REPORT_DIR / "54_inventario_nacional_humedales_metadatos.json"
    report.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Archivo: {FINAL}\nMetadatos: {report}\nPASO 54 FINALIZADO", flush=True)


if __name__ == "__main__":
    main()
