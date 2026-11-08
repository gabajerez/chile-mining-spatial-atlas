# Paso 63b: conciliación nacional y zonas cartografiadas

Los balances de los seis paneles del paso 61 se validan con la misma tolerancia geométrica utilizada al construirlos. Los indicadores numéricos son los ya calculados, sin alteración.

| Ámbito | Humedales (ha) | Concesionada (ha) | Coincidencia (%) |
|---|---:|---:|---:|
| norte | 721,330.09 | 550,933.28 | 76.38 |
| centro | 107,152.07 | 33,924.53 | 31.66 |
| norte_y_centro | 828,482.15 | 584,857.81 | 70.59 |
| resto_no_cartografiado | 4,542,586.03 | 29,876.31 | 0.66 |
| ambito_343_comunas | 5,371,068.19 | 614,734.12 | 11.45 |

## Limitaciones

El resto no cartografiado proviene de una resta aritmética y no equivale a una intersección geoespacial independiente. Los ámbitos regionales son subconjuntos del universo de 343 comunas; las concesiones no identifican mineral y el residual es provisional.

## Insumos

- `C:/Users/Gabriela_Jerez/Desktop/MAPAS_GM/reports/enmc/58_overlap_humedales_mma_resumen.csv`
- `C:/Users/Gabriela_Jerez/Desktop/MAPAS_GM/reports/enmc/61_control_overlap_cartografico_mma.csv`
- `C:/Users/Gabriela_Jerez/Desktop/MAPAS_GM/reports/enmc/62_auditoria_ambitos_58_61.json`
