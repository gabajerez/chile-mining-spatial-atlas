# Coincidencia de humedales MMA y concesiones mineras (pasos 54-59)

## Universo y procedencia
- Servicio: Inventario Nacional de Humedales MMA (SIMBIO, FeatureServer/0); descarga documentada en el paso 54.
- Registros anunciados: 117.983; geometrías utilizables: 117.969; sin geometría: 14 (registrados, no reemplazados).
- Proyección de área: EPSG:6933.
- Ámbito de análisis: 343 comunas, superficie de estudio 75.256.754,28 ha.
- Coincidencia con concesiones constituidas y residual: archivos preparados en paso 35.
- Cálculo por 110 teselas disjuntas, intersección exacta y superficie única tras unión dentro de cada tesela (paso 58).

## Resultados dentro del ámbito de estudio
- Superficie única de humedales: **5,371,068.19 ha**.
- Coincidencia con concesiones constituidas: **614,734.12 ha (11.4453 %)**.
- Residual concesional provisional: **582,505.18 ha (10.8452 %)**.
- Coincidencia de concesión con huella OA seleccionada: **32,228.94 ha (0.6000 %)**.
- Sin coincidencia concesional: **4,756,334.07 ha (88.5547 %)**.
- Balance: concesión constituida = residual provisional + coincidencia con huella OA (dentro de la superficie de humedales), con error numérico despreciable.

## Alcance y limitaciones
Los resultados miden **superposición espacial** con derechos mineros constituidos. No demuestran intervención, explotación, daño ambiental ni asociación de las concesiones a minerales críticos. La categoría residual es provisional porque depende de la selección de unidades OA y aún no descuenta nuevas huellas de proyectos COCHILCO verificadas. La cifra previa de 35,66 % se calculó sobre una fuente distinta, restringida a tres regiones, y no es directamente comparable. La distribución nacional de humedales afecta el denominador. Validar metadatos temáticos y temporales de la fuente MMA antes de publicación.

## Reproducibilidad
Ejecutar `python src/59_validar_y_visualizar_overlap_humedales.py` tras el paso 58. Entradas: `reports/enmc/58_overlap_humedales_mma_resumen.csv`, `58_overlap_humedales_mma_teselas.csv` y `58_overlap_humedales_mma_control.json`. Salidas: `reports/enmc/59_control_balance_humedales_mma.json`, `outputs/figures/enmc/59_balance_humedales_mma_concesiones.png` y `.svg`. Datos geoespaciales grandes se gestionan separadamente de Git; preservar rutas, fuentes y metadatos.
