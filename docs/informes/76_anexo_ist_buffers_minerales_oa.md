# Anexo de resultados ENMC — Paso 76

> **Alcance:** consolidación documental de los archivos `76_resumen_fuentes.csv` y `76_oa_resumen_por_mineral.csv`. Los resultados son reproducidos de los CSV y no constituyen una auditoría independiente de las geometrías o atributos originales.

## Diseño geométrico

- OA: 292 huellas poligonales seleccionadas, con las dos geometrías inválidas reparadas y auditadas en el paso 75b.
- Proyectos: 55 localizaciones representadas por buffers circulares hipotéticos cuya superficie objetivo corresponde a la **mediana de las áreas OA: 115,682626 ha** (diámetro circular teórico de **1.213,638 m**).
- El buffer no representa la huella física de intervención futura. La equiparación por mediana no iguala los tamaños individuales OA ni las formas geométricas.
- Se conserva el análisis puntual de los pasos 66–69f como comparación metodológica separada.

## Comparación entre fuentes

| Fuente | Unidades | IST medio | Mediana | Mínimo | Máximo |
|---|---:|---:|---:|---:|---:|
| COCHILCO_ENMC | 55 | 26,211 | 23,675 | 1,750 | 73,125 |
| OA_ENMC | 292 | 31,053 | 30,038 | 0,000 | 83,675 |

**Diferencia de medias OA − proyectos:** 4,842 puntos.

## Análisis de huellas OA por mineral

| Mineral | Huellas asociadas | IST medio | IST mediano | Suma de áreas individuales (ha) |
|---|---:|---:|---:|---:|
| cobre | 194 | 32,709 | 31,025 | 187.491,37 |
| hierro | 45 | 29,442 | 30,925 | 12.664,64 |
| oro | 44 | 31,732 | 33,013 | 22.740,87 |
| plata | 22 | 35,043 | 33,725 | 14.567,73 |
| yodo | 13 | 20,048 | 17,050 | 47.459,43 |
| litio | 5 | 30,725 | 35,325 | 28.904,34 |
| molibdeno | 3 | 16,117 | 13,025 | 6.997,60 |
| tierras_raras | 1 | 50,975 | 50,975 | 65,22 |

**Control de multietiquetas:** 327 asociaciones mineral–huella para 292 unidades OA. El número de asociaciones no representa polígonos OA adicionales. Las sumas de superficies por categoría tampoco deben agregarse como una superficie nacional exclusiva.

## Contribución media al IST por mineral (puntos del índice)

| Mineral | AP | SB | GL | HU | AI | CI | AD | PO | TU | IST medio |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cobre | 3,381 | 4,912 | 0,806 | 6,943 | 5,915 | 5,250 | 0,611 | 3,347 | 1,544 | 32,709 |
| hierro | 3,575 | 6,380 | 0,000 | 4,733 | 4,061 | 6,404 | 0,000 | 2,878 | 1,410 | 29,442 |
| oro | 4,969 | 4,894 | 1,511 | 8,386 | 4,443 | 3,498 | 0,148 | 2,307 | 1,576 | 31,732 |
| plata | 5,250 | 5,513 | 1,814 | 9,955 | 4,830 | 3,424 | 0,295 | 2,148 | 1,816 | 35,043 |
| yodo | 6,346 | 1,523 | 0,000 | 2,769 | 2,288 | 1,260 | 1,625 | 1,615 | 2,621 | 20,048 |
| litio | 5,775 | 5,940 | 0,000 | 11,400 | 0,000 | 1,965 | 2,600 | 1,400 | 1,645 | 30,725 |
| molibdeno | 2,750 | 1,650 | 0,000 | 0,000 | 2,833 | 1,092 | 0,000 | 5,833 | 1,958 | 16,117 |
| tierras_raras | 12,375 | 7,425 | 0,000 | 12,000 | 0,000 | 9,825 | 0,000 | 7,000 | 2,350 | 50,975 |

Las nueve contribuciones de cada fila suman el IST medio mostrado (salvo redondeo). Los valores son **puntos de índice ponderados**, no porcentajes de coincidencia concesional ni distancias.

## Lectura metodológica y restricciones

1. El IST poligonal OA y el IST sobre buffers COCHILCO miden proximidad desde superficies. No deben confundirse con el IST puntual homologado (OA 28,291952; proyectos 25,066818).
2. Las categorías minerales OA son multietiqueta; las comparaciones entre grupos describen subconjuntos superpuestos. Las clases con muy pocos registros no sustentan generalizaciones.
3. El campo de mineral presente en OA no convierte a las concesiones constituidas en concesiones clasificadas por mineral. Los cruces por mineral solo pueden asociarse con las huellas/proyectos identificados.
4. El carácter activo de las 292 huellas OA no está acreditado individualmente: describirlas como **huellas registradas seleccionadas** y no como operaciones activas verificadas.
5. Los resultados por componente reutilizan las fuentes normalizadas del IST, incluidos los humedales nacionales MMA. Conservar en la metodología las limitaciones de cobertura y representatividad de las otras fuentes.

## Archivos fuente y resultados vinculables en GitHub

- [`76_resumen_fuentes.csv`](../../reports/enmc/76_resumen_fuentes.csv)
- [`76_oa_resumen_por_mineral.csv`](../../reports/enmc/76_oa_resumen_por_mineral.csv)
- [`76_ist_poligonos_buffers.csv`](../../reports/enmc/76_ist_poligonos_buffers.csv)
- [`76_oa_unidades_por_mineral.csv`](../../reports/enmc/76_oa_unidades_por_mineral.csv)
- [`76_oa_mineral_por_region.csv`](../../reports/enmc/76_oa_mineral_por_region.csv)
- [`75_control_buffers_mediana_oa.json`](../../reports/enmc/75_control_buffers_mediana_oa.json)
- [`75_auditoria_geometrias_oa.csv`](../../reports/enmc/75_auditoria_geometrias_oa.csv)
- [`75b_buffers_equivalentes_mediana_oa.py`](../../src/75b_buffers_equivalentes_mediana_oa.py)
- [`76_ist_poligonos_buffers_y_minerales_oa.py`](../../src/76_ist_poligonos_buffers_y_minerales_oa.py)

> **Nota de publicación:** comprobar que los archivos anteriores estén efectivamente incorporados al commit antes de habilitar los enlaces; los GeoPackage grandes permanecen fuera de Git.
