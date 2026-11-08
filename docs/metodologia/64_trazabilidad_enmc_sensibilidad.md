# Minerales críticos en Chile: sensibilidad territorial y coincidencia concesional

## Alcance y estado de resultados

Este módulo analiza tres representaciones espaciales diferentes: (i) la huella minera registrada de la selección de minerales de la Estrategia Nacional de Minerales Críticos (OA; 292 unidades candidatas, **sin verificación individual de operación vigente**), (ii) la localización puntual representativa de 55 proyectos de inversión de COCHILCO (**no constituye huella de intervención**) y (iii) concesiones mineras constituidas, independientemente del mineral, con un residual provisional obtenido al descontar la huella OA seleccionada. Las concesiones no cuentan con atributo de mineral crítico. El residual no equivale a una reserva minera ni a proyectos confirmados.

El ámbito común de los cálculos de superficie comprende 343 comunas (75.256.754,28 ha en EPSG:6933). Las dos zonas cartografiadas —Norte Grande/Norte Chico y zona central— están íntegramente contenidas en ese ámbito, pero no lo agotan. Para agregación por superficies se emplean geometrías sin simplificar y teselas disjuntas; la simplificación se reserva para representación cartográfica.

## Índice de Sensibilidad Territorial (IST)

El IST es un indicador de **proximidad geográfica ponderada**, no una estimación de impacto, riesgo ambiental constatado o vulneración jurídica. Se calcula para 292 unidades OA y 55 localizaciones COCHILCO (347 entidades). Nueve componentes, derivados de once capas, contribuyen mediante puntajes por distancia de 1, 0,75, 0,5, 0,25 o 0 según bandas y máximos por componente.

| Componente | Peso | Bandas de distancia (km) |
| --- | ---: | --- |
| Áreas protegidas | 16,5 % | 1, 5, 10, 25 |
| Sitios prioritarios y reservas de biosfera (conjunto) | 9,9 % | 1, 5, 10, 25 |
| Glaciares | 13,3 % | 0,5, 2, 10, 25 |
| Humedales | 12,0 % | 1, 5, 10, 25 |
| Planes atmosféricos | 17,0 % | 0,5, 5, 25, 50 |
| Comunidades indígenas | 13,1 % | 2, 10, 25, 50 |
| Áreas de desarrollo indígena | 6,5 % | 2, 10, 25, 50 |
| Áreas pobladas | 7,0 % | 2, 5, 15, 30 |
| Atractivos y zonas de interés turístico (conjunto) | 4,7 % | 0,5, 2, 5, 10 |

Suma de pesos: 100 %. Las distancias se estiman con proyecciones locales equidistantes por unidad. Fórmula general: `IST = 100 * sum(peso_fraccional * puntaje_componente)`.

## Auditoría de humedales y cambio de versión

La capa inicial (`39_humedales.gpkg`) contenía 4.801 geometrías con presencia en solo tres regiones. No debía utilizarse como inventario nacional exhaustivo. Se obtuvo una nueva instantánea del servicio oficial **MMA/SIMBIO, Inventario Nacional de Humedales**:

`https://arcgis.mma.gob.cl/server/rest/services/SIMBIO/SIMBIO_HUMEDALES/FeatureServer/0`

El servicio informó 117.983 identificadores: 117.969 con geometría utilizable y 14 sin ella (identificadores documentados en `54b_geometrias_no_utilizables.csv`). Se validó presencia en 16/16 regiones, geometrías válidas y normalización a EPSG:6933. Una reparación topológica posterior a la reproyección se documentó por separado (`56b_reparaciones_geometricas.csv`). La presencia nacional no sustituye una revisión de clasificación temática, fechas de actualización, definición de humedal ni calidad posicional.

Se sustituyó **solo el componente humedales** del IST, con peso 12 %:

`IST_actualizado = IST_previo + 12 * (S_HU_MMA - S_HU_previo)`.

| Universo | n | Cambios | Promedio previo | Promedio actualizado | Diferencia media |
| --- | ---: | ---: | ---: | ---: | ---: |
| OA | 292 | 224 | 24,9297 | 31,0530 | +6,1233 |
| COCHILCO | 55 | 42 | 20,2123 | 25,0668 | +4,8545 |

Total: 266/347 entidades modificadas, todas con aumentos; variación máxima +12 puntos. Los ocho componentes restantes permanecen sin cambio. La fuente previa y su resultado se preservan con fines de trazabilidad, no como valor actualizado de cobertura nacional.

## Coincidencia con concesiones constituidas: resultados de humedales MMA

**Denominador:** superficie **única** del inventario MMA dentro del ámbito de 343 comunas, no suma bruta de polígonos ni totalidad de humedales del país. Cálculo exacto en EPSG:6933, 110 teselas de 120 km, con unión por tesela para evitar doble conteo.

| Categoría mutuamente excluyente | Superficie (ha) | Fracción del total |
| --- | ---: | ---: |
| Sin coincidencia con concesión constituida | 4.756.334,065 | 88,5547 % |
| Coincidente con residual provisional | 582.505,176 | 10,8452 % |
| Coincidente con concesión y OA seleccionada | 32.228,945 | 0,6000 % |
| **Superficie total de humedales en el ámbito** | **5.371.068,186** | **100 %** |

La superficie total coincidente con concesiones constituidas es **614.734,121 ha (11,4453 %)**. No existe atributo de mineral crítico en las concesiones. La coincidencia no demuestra actividad, impacto o conflicto constatado.

### Conciliación por zonas cartografiadas

| Ámbito | Humedales (ha) | Coincidencia concesional (ha) | Proporción |
| --- | ---: | ---: | ---: |
| Norte Grande/Norte Chico | 721.330,09 | 550.933,28 | 76,38 % |
| Zona central | 107.152,07 | 33.924,53 | 31,66 % |
| Norte y centro | 828.482,15 | 584.857,81 | 70,59 % |
| Resto del ámbito, **por diferencia** | 4.542.586,03 | 29.876,31 | 0,66 % |
| Ámbito de 343 comunas | 5.371.068,19 | 614.734,12 | 11,45 % |

Las máscaras de norte y centro están contenidas en el ámbito nacional y no se superponen. El «resto» es un residuo aritmético conciliado, **no** un cálculo independiente sobre polígonos. Los porcentajes regionales no se suman: tienen denominadores diferentes. El valor antiguo de 35,66 % se calculó sobre una fuente de humedales espacialmente limitada y no es directamente comparable con el indicador MMA actualizado.

## Archivos, reproducibilidad y control de versiones

- **Cálculo:** `src/43_calcular_ist_enmc.py`, `src/57_recalcular_ist_humedales_mma.py`, `src/58_recalcular_overlap_humedales_mma.py`.
- **Validación:** `src/53_auditar_cobertura_sensibilidad.py`, `src/55_validar_inventario_humedales_nacional.py`, `src/56b_reanudar_normalizacion_humedales.py`, `src/59_validar_y_visualizar_overlap_humedales.py`, `src/62_auditar_ambitos_overlap_mma.py`, `src/63b_conciliar_humedales_nacional_zonas.py`.
- **Cartografía:** `src/60_actualizar_mapas_ist_humedales_mma.py` y `src/61_mapas_coincidencia_humedales_mma.py`.
- **Metadatos y resultados:** `reports/enmc/54b_*`, `55_*`, `56b_*`, `57_*`, `58_*`, `59_*`, `60_*`, `61_*`, `62_*` y `63_*` (excluyendo checkpoints locales); `docs/metodologia/59_resultados_humedales_mma.md` y `63_conciliacion_humedales_nacional_zonas.md`.
- **Datos geoespaciales:** `data/raw/`, `data/external/` y `data/processed/` se mantienen fuera de Git; se documentan las fuentes y los procedimientos para recrearlos. La disponibilidad futura de servicios externos no está garantizada.

Los scripts históricos fallidos o superados se conservan como trazabilidad, pero las versiones vigentes se identifican explícitamente arriba. La normalización y la reparación deben seguir auditándose sobre los archivos de control antes de cualquier recálculo futuro. No se cargan automáticamente geodatos grandes ni archivos temporales al repositorio.

## Limitaciones pendientes para publicación

1. Verificar metadatos oficiales, fecha, cobertura temática y posibles solapamientos entre clases del inventario MMA.
2. Revisar individualmente el estado operacional de las 292 unidades OA; no equiparar «huella registrada» con mina operativa.
3. Identificar geometrías oficiales de nuevos proyectos cuando existan; los 55 proyectos COCHILCO son puntos representativos, no huellas de inversión.
4. Validar el residual concesional ante proyectos con nueva huella y regímenes especiales, incluidos salares y litio.
5. Distinguir en el manuscrito las estadísticas de proximidad (IST) de los solapamientos superficiales; ninguno prueba daño o impacto.
6. El ámbito común corresponde a 343 comunas y no debe describirse automáticamente como toda la superficie nacional.
