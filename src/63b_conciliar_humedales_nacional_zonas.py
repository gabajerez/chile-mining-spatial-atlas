#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paso 63b. Conciliación numérica 58/61/62 con tolerancias trazables.

Lee exclusivamente tablas e informe del análisis existente. No altera geodatos.
Distingue la tolerancia de áreas geométricas de la tolerancia de los balances
aritméticos de CSV; inspecciona solo las dos filas 'humedales' para la
conciliación solicitada, pero informa cualquier alerta en otros componentes.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REP = ROOT / "reports" / "enmc"
DOC = ROOT / "docs" / "metodologia"
TOL_HA = 0.02


def check(condition, message):
    if not condition:
        raise ValueError(message)


def fmt(v):
    return f"{v:,.2f}"


def main():
    print("=== PASO 63b: CONCILIACION HUMEDALES MMA / ZONAS ===", flush=True)
    national_csv = REP / "58_overlap_humedales_mma_resumen.csv"
    zonal_csv = REP / "61_control_overlap_cartografico_mma.csv"
    audit_json = REP / "62_auditoria_ambitos_58_61.json"
    for p in (national_csv, zonal_csv, audit_json):
        check(p.exists(), f"No se encuentra: {p}")

    a = pd.read_csv(national_csv, encoding="utf-8-sig")
    b = pd.read_csv(zonal_csv, encoding="utf-8-sig")
    audit = json.loads(audit_json.read_text(encoding="utf-8"))
    check(len(a) == 1, "Se espera exactamente una fila nacional (paso 58)")
    check(int(a.iloc[0]["n_comunas_ambito"]) == 343, "Ambito nacional no contiene 343 comunas")
    check(int(a.iloc[0]["n_teselas"]) == 110, "Paso 58 no contiene 110 teselas")
    check("norte_centro_solapamiento_ha" in audit, "Paso 62 sin comprobacion de solapamiento")
    check("ambito_nacional_comunal_ha" in audit, "Paso 62 sin ambito comunal")
    check(float(audit["norte_centro_solapamiento_ha"]) <= TOL_HA,
          "Las dos zonas se superponen: no es valido sumar sus superficies")

    required = {"zona", "componente", "sensible_ha", "concesionada_ha",
                "residual_ha", "coincidente_oa_ha", "no_concesionada_ha",
                "error_balance_m2"}
    check(required.issubset(b.columns), f"Columnas faltantes en paso 61: {sorted(required-set(b.columns))}")
    check(not b.duplicated(["zona", "componente"]).any(),
          "El reporte 61 tiene zonas/componentes duplicados")

    # 61 checked abs(error_balance_m2) <= max(1 m2, area_m2*1e-8).
    # 63 original erroneously demanded <1 m2 for every component.
    per_row_tolerance_m2 = (b["sensible_ha"].abs() * 10000 * 1e-8).clip(lower=1.0)
    b = b.copy()
    b["tolerancia_paso61_m2"] = per_row_tolerance_m2
    b["balance_compatible_paso61"] = b["error_balance_m2"].abs() <= per_row_tolerance_m2 + 1e-5
    alerts = b.loc[~b["balance_compatible_paso61"]]
    check(alerts.empty,
          "Hay balances que exceden incluso la tolerancia del paso 61: " +
          alerts[["zona", "componente", "error_balance_m2", "tolerancia_paso61_m2"]].to_string(index=False))
    print("Balances de los 6 paneles compatibles con tolerancias del paso 61", flush=True)

    d = b.loc[b["componente"].astype(str).str.strip().str.lower() == "humedales"].copy()
    check(len(d) == 2 and set(d["zona"].str.lower()) == {"norte", "centro"},
          "Se necesitan exactamente los dos registros de humedales del paso 61")
    base = a.iloc[0]
    nat = {
        "humedales_ha": float(base["superficie_sensible_unica_ha"]),
        "concesionada_ha": float(base["superficie_sensible_concesionada_ha"]),
        "residual_ha": float(base["superficie_sensible_residual_provisional_ha"]),
        "oa_ha": float(base["superficie_sensible_concesionada_coincidente_oa_ha"]),
    }
    records = []
    for _, r in d.iterrows():
        h, c, res, oa, libre = (float(r[key]) for key in (
            "sensible_ha", "concesionada_ha", "residual_ha", "coincidente_oa_ha", "no_concesionada_ha"))
        check(all(x >= -TOL_HA for x in (h, c, res, oa, libre)),
              f"Superficie negativa en {r['zona']}")
        # CSV totals may have very small numerical differences.
        check(abs(h-(libre+res+oa)) <= max(TOL_HA, h * 1e-8),
              f"Balance H = libre + residual + OA no cierra en {r['zona']}")
        check(abs(c-(res+oa)) <= max(TOL_HA, h * 1e-8),
              f"Balance C = residual + OA no cierra en {r['zona']}")
        records.append({"ambito": str(r["zona"]), "humedales_ha": h,
                        "concesionada_ha": c, "residual_ha": res, "oa_ha": oa,
                        "sin_concesion_ha": libre,
                        "porcentaje_concesionado": 100*c/h if h else None,
                        "origen": "61_interseccion_zonal"})

    keys = ("humedales_ha", "concesionada_ha", "residual_ha", "oa_ha")
    totals = {k: sum(row[k] for row in records) for k in keys}
    remainder = {k: nat[k]-totals[k] for k in keys}
    check(all(v >= -TOL_HA for v in remainder.values()),
          f"Las sumas zonales exceden al nacional: {remainder}. "
          "No resolverlo ampliando tolerancias; revisar ámbitos y método")
    check(abs(nat["concesionada_ha"]-nat["residual_ha"]-nat["oa_ha"]) <= TOL_HA,
          "El balance nacional del paso 58 no cierra")
    for name, values, provenance in (
        ("norte_y_centro", totals, "suma_61"),
        ("resto_no_cartografiado", remainder, "diferencia_58_menos_61"),
        ("ambito_343_comunas", nat, "58_nacional"),
    ):
        h, c, res, oa = (values[k] for k in keys)
        records.append({"ambito": name, "humedales_ha": h,
                        "concesionada_ha": c, "residual_ha": res, "oa_ha": oa,
                        "sin_concesion_ha": h-c,
                        "porcentaje_concesionado": 100*c/h if h else None,
                        "origen": provenance})

    REP.mkdir(parents=True, exist_ok=True)
    DOC.mkdir(parents=True, exist_ok=True)
    output_csv = REP / "63_conciliacion_humedales_nacional_zonas.csv"
    output_json = REP / "63_control_conciliacion_humedales.json"
    output_md = DOC / "63_conciliacion_humedales_nacional_zonas.md"
    pd.DataFrame(records).to_csv(output_csv, index=False,
                                 encoding="utf-8-sig", float_format="%.8f")
    control = {
        "paso": "63b", "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "estado": "BALANCE_ARITMETICO_COMPATIBLE_REMANENTE_NO_RECALCULADO",
        "criterio_balance_61": "abs(error_balance_m2) <= max(1, sensible_ha*10000*1e-8)",
        "tolerancia_balance_csv_ha": TOL_HA,
        "registros_61_revisados": len(b),
        "mayor_error_61_m2": float(b["error_balance_m2"].abs().max()),
        "resto_no_cartografiado_ha": remainder,
        "fuentes": [national_csv.name, zonal_csv.name, audit_json.name],
        "advertencias": [
            "Resto no cartografiado calculado por resta, no interseccion espacial independiente.",
            "Se preservan sin modificaciones todas las superficies de los pasos 58 y 61.",
            "La tolerancia geometrica del paso 61 es proporcional a la superficie sensible.",
            "Las concesiones no tienen atributo de mineral; el residual y la seleccion OA son provisionales.",
            "Coincidencia concesional no demuestra actividad ni impactos ambientales.",
        ],
    }
    output_json.write_text(json.dumps(control, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# Paso 63b: conciliación nacional y zonas cartografiadas", "",
             "Los balances de los seis paneles del paso 61 se validan con la misma tolerancia geométrica utilizada al construirlos. Los indicadores numéricos son los ya calculados, sin alteración.", "",
             "| Ámbito | Humedales (ha) | Concesionada (ha) | Coincidencia (%) |",
             "|---|---:|---:|---:|"]
    for r in records:
        lines.append(f"| {r['ambito']} | {fmt(r['humedales_ha'])} | {fmt(r['concesionada_ha'])} | {r['porcentaje_concesionado']:.2f} |")
    lines += ["", "## Limitaciones", "",
              "El resto no cartografiado proviene de una resta aritmética y no equivale a una intersección geoespacial independiente. Los ámbitos regionales son subconjuntos del universo de 343 comunas; las concesiones no identifican mineral y el residual es provisional.", "",
              "## Insumos", "", f"- `{national_csv.as_posix()}`", f"- `{zonal_csv.as_posix()}`", f"- `{audit_json.as_posix()}`", ""]
    output_md.write_text("\n".join(lines), encoding="utf-8")
    for row in records:
        print(f"  {row['ambito']}: H={fmt(row['humedales_ha'])} ha | "
              f"C={fmt(row['concesionada_ha'])} ha | {row['porcentaje_concesionado']:.2f}%", flush=True)
    print("Salida:", output_csv, output_json, output_md, sep="\n  ", flush=True)
    print("PASO 63b FINALIZADO", flush=True)


if __name__ == "__main__":
    main()
