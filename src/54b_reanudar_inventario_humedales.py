"""Paso 54b: reanudar descarga del Inventario Nacional de Humedales (MMA/SIMBIO).

Conserva el .partial.gpkg del paso 54. Retiene todos los IDs consultados en
el control, pero excluye del GeoPackage aquellos sin geometría poligonal
utilizable. No sustituye la fuente de trabajo ni recalcula indicadores.
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
import requests
from shapely import force_2d, make_valid
from shapely.geometry import MultiPolygon, Polygon

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://arcgis.mma.gob.cl/server/rest/services/SIMBIO/SIMBIO_HUMEDALES/FeatureServer/0"
OUT = ROOT / "data/raw/sensibilidad/humedales_nacional_mma"
REP = ROOT / "reports/enmc"
PARTIAL = OUT / "54_inventario_nacional_humedales.partial.gpkg"
FINAL = OUT / "54_inventario_nacional_humedales.gpkg"
SKIPPED = REP / "54b_geometrias_no_utilizables.csv"
METADATA = REP / "54b_inventario_nacional_humedales_metadatos.json"
LAYER = "humedales_mma"


def request_json(session, url, params, retries=5):
    for i in range(retries):
        try:
            r = session.get(url, params=params, timeout=(20, 180))
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                raise RuntimeError(str(data["error"]))
            return data
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            if i == retries - 1:
                raise RuntimeError(f"Servicio no respondió correctamente: {exc}") from exc
            time.sleep(min(2 ** i, 20))


def polygon_parts(geom):
    if geom is None or geom.is_empty:
        return []
    if not geom.is_valid:
        geom = make_valid(geom)
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom] if geom.area > 0 else []
    if geom.geom_type == "MultiPolygon":
        return [p for p in geom.geoms if not p.is_empty and p.area > 0]
    if geom.geom_type == "GeometryCollection":
        pieces = []
        for part in geom.geoms:
            pieces.extend(polygon_parts(part))
        return pieces
    return []


def normalize_geom(geom):
    if geom is None or geom.is_empty:
        return None
    try:
        parts = polygon_parts(force_2d(geom))
        return MultiPolygon(parts) if parts else None
    except Exception:
        return None


def existing_ids(path):
    if not path.exists():
        return set()
    # Leer solo la columna de identificador, sin cargar 100.000 polígonos.
    columns = pyogrio.read_dataframe(path, layer=LAYER, columns=["OBJECTID"], read_geometry=False)
    if "OBJECTID" not in columns:
        raise ValueError(f"No existe OBJECTID en {path}")
    ids = pd.to_numeric(columns["OBJECTID"], errors="raise").astype("int64")
    if ids.duplicated().any():
        raise ValueError("El archivo parcial tiene OBJECTID duplicados: revisar antes de continuar")
    return set(ids.tolist())


def read_skipped():
    if not SKIPPED.exists():
        return {}
    tab = pd.read_csv(SKIPPED)
    return {int(row.OBJECTID): str(row.motivo) for row in tab.itertuples(index=False)}


def write_skipped(skips):
    pd.DataFrame(
        [{"OBJECTID": k, "motivo": v} for k, v in sorted(skips.items())],
        columns=["OBJECTID", "motivo"],
    ).to_csv(SKIPPED, index=False, encoding="utf-8-sig")


def process_batch(session, chunk):
    payload = request_json(session, ENDPOINT + "/query", {
        "objectIds": ",".join(map(str, chunk)),
        "outFields": "*", "returnGeometry": "true", "outSR": 4326, "f": "geojson",
    })
    features = payload.get("features")
    if not isinstance(features, list):
        raise RuntimeError(f"Respuesta sin features para lote: {chunk[:3]}...")
    if not features:
        raise RuntimeError(f"Respuesta vacía para {len(chunk)} IDs; no se excluirán como faltantes")
    frame = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
    if "OBJECTID" not in frame:
        raise RuntimeError("Respuesta sin campo OBJECTID")
    returned = pd.to_numeric(frame.OBJECTID, errors="raise").astype("int64")
    if returned.duplicated().any() or set(returned) != set(chunk):
        raise RuntimeError("Servidor devolvió IDs diferentes/incompletos. Reintentar; no se alteró el lote")
    frame["OBJECTID"] = returned
    skip = {}
    normalized = []
    for oid, geom in zip(returned, frame.geometry):
        corrected = normalize_geom(geom)
        if corrected is None:
            skip[int(oid)] = "Geometría ausente, vacía o sin superficie poligonal válida"
        normalized.append(corrected)
    frame.geometry = normalized
    valid = frame.loc[frame.geometry.notna()].copy()
    return valid, skip


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-size", type=int, default=100)
    args = ap.parse_args()
    if not 1 <= args.batch_size <= 500:
        ap.error("--batch-size debe estar entre 1 y 500")
    OUT.mkdir(parents=True, exist_ok=True)
    REP.mkdir(parents=True, exist_ok=True)
    print("=== PASO 54b: REANUDAR HUMEDALES MMA ===", flush=True)
    if FINAL.exists():
        raise FileExistsError(f"Ya existe archivo final: {FINAL}. No se sobrescribirá.")

    stored = existing_ids(PARTIAL)
    skipped = read_skipped()
    print(f"Recuperados del GeoPackage parcial: {len(stored)} registros", flush=True)
    print(f"IDs sin geometría previamente documentados: {len(skipped)}", flush=True)
    with requests.Session() as session:
        session.headers.update({"User-Agent": "MAPAS_GM-ENMC-research/1.0"})
        service = request_json(session, ENDPOINT, {"f": "json"})
        if service.get("geometryType") != "esriGeometryPolygon":
            raise RuntimeError("El servicio ya no publica polígonos")
        raw_ids = request_json(session, ENDPOINT + "/query", {
            "where": "1=1", "returnIdsOnly": "true", "f": "json",
        }).get("objectIds") or []
        ids = set(map(int, raw_ids))
        if len(raw_ids) != len(ids):
            raise RuntimeError("IDs duplicados en el servicio")
        declared = int(request_json(session, ENDPOINT + "/query", {
            "where": "1=1", "returnCountOnly": "true", "f": "json",
        })["count"])
        if len(ids) != declared:
            raise RuntimeError("Conteo del servicio y lista de IDs no coinciden")
        if not stored.issubset(ids) or not set(skipped).issubset(ids):
            raise RuntimeError("El servicio ha cambiado: hay IDs antiguos que ya no existen")
        if stored.intersection(skipped):
            raise RuntimeError("Existen IDs a la vez guardados y documentados como excluidos")
        remaining = sorted(ids - stored - set(skipped))
        print(f"Servidor: {declared} IDs | Pendientes: {len(remaining)}", flush=True)
        with warnings.catch_warnings():
            # El GPKG anterior usa POLYGON pero contiene MultiPolygon. No se cambia
            # el esquema ya escrito; después validamos y exportamos uno conforme.
            warnings.filterwarnings("ignore", message="A geometry of type MULTIPOLYGON is inserted")
            for offset in range(0, len(remaining), args.batch_size):
                chunk = remaining[offset:offset + args.batch_size]
                valid, absent = process_batch(session, chunk)
                # Primero se agregan geometrías válidas: ante interrupción, el
                # siguiente intento recupera los OBJECTID directamente del GPKG.
                if len(valid):
                    valid.to_file(PARTIAL, layer=LAYER, driver="GPKG", engine="pyogrio",
                                  append=PARTIAL.exists(), index=False)
                    stored.update(map(int, valid.OBJECTID))
                skipped.update(absent)
                write_skipped(skipped)
                if (offset // args.batch_size + 1) % 10 == 0 or offset + len(chunk) >= len(remaining):
                    print(f"  Procesados: {min(offset+len(chunk), len(remaining))}/{len(remaining)} "
                          f"| Guardados acumulados: {len(stored)} | Sin geometría: {len(skipped)}", flush=True)

    stored_disk = existing_ids(PARTIAL)
    if stored_disk != stored or stored_disk.intersection(skipped) or stored_disk | set(skipped) != ids:
        raise RuntimeError("Control de integridad falló: revisar los IDs antes de finalizar")
    info = pyogrio.read_info(PARTIAL, layer=LAYER)
    if int(info["features"]) != len(stored_disk):
        raise RuntimeError("El recuento físico del GeoPackage no coincide con los IDs")

    # Conservamos archivo parcial como respaldo y publicamos un archivo final
    # idéntico. No se realizan conversiones masivas que puedan agotar memoria.
    shutil.copy2(PARTIAL, FINAL)
    metadata = {
        "fuente": "MMA / SIMBIO - Inventario Nacional de Humedales",
        "url_servicio": ENDPOINT,
        "fecha_validacion_utc": datetime.now(timezone.utc).isoformat(),
        "ids_servidor": declared,
        "geometrias_poligonales_guardadas": len(stored_disk),
        "ids_sin_geometria_utilizable": len(skipped),
        "geometrias_excluidas_detalle": str(SKIPPED.relative_to(ROOT)),
        "crs_salida": str(info.get("crs")),
        "limites_fuente": "Pendiente verificar distribución regional, categorías y temporalidad",
        "archivo": str(FINAL.relative_to(ROOT)),
        "nota_formato": "Archivo parcial original usa geometría declarada POLYGON; algunas entidades son MultiPolygon. Normalizar al preparar la capa analítica.",
        "advertencia": "No sustituir datos en análisis IST/superposición hasta auditoría territorial y geométrica",
    }
    METADATA.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Verificados: {declared} IDs = {len(stored_disk)} con geometría + {len(skipped)} sin geometría", flush=True)
    print(f"Final: {FINAL}\nMetadatos: {METADATA}\nExclusiones: {SKIPPED}", flush=True)
    print("PASO 54b FINALIZADO", flush=True)


if __name__ == "__main__":
    main()
