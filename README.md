# MAPAS_GM

Proyecto de análisis espacial y estadística exploratoria sobre actividad minera en Chile, integrando tres fuentes principales:

1. **OA**: polígonos de actividad/proyectos mineros.
2. **SERNAGEOMIN**: concesiones mineras.
3. **COCHILCO**: cartera futura de proyectos.

## Objetivo

Construir una base reproducible para explorar la distribución territorial de la actividad minera en Chile a escala regional y comunal, generando:

- indicadores de cobertura territorial;
- integración espacial entre capas;
- análisis específico de cobre;
- mapas regionales y comunales;
- productos estadísticos aptos para difusión pública.

## Fuentes utilizadas

- OA-2-Articulo.shp
- Cartera de proyecto COCHILCO.shp
- sernageomin_concesiones_2026-06-05.geojson
- Cartografía administrativa 2022 (comunas y regiones)

## Principales salidas

### Tablas
- `outputs/tables/matriz_mineria_comunal_v1.csv`
- `outputs/tables/matriz_mineria_regional_v1.csv`
- `outputs/tables/matriz_cobre_comunal_v1.csv`
- `outputs/tables/matriz_cobre_regional_v1.csv`

### Mapas
- `outputs/maps/regionales_comunas/`
- `outputs/maps/regionales_cobre/`

### Figuras atlas
- `outputs/figures/atlas/01_comparacion_cobertura_regional.png`
- `outputs/figures/atlas/02_relacion_oa_concesiones_comunal.png`
- `outputs/figures/atlas/03_superficie_cobre_regional.png`

## Resultados destacados

- Superficie OA: **343.699 ha**
- Concesiones constituidas: **16.239.454 ha**
- Cobertura territorial integrada: **16.257.709 ha**
- Superficie vinculada al cobre: **185.695 ha**
- Proyectos COCHILCO: **57**
- Proyectos COCHILCO de cobre: **40**

## Reproducibilidad

Los scripts están numerados secuencialmente en `src/` y pueden ejecutarse desde PowerShell dentro del entorno Conda `mapas_gm`.

## Notas metodológicas

- La cobertura de concesiones no equivale a superficie efectivamente intervenida.
- Las superficies OA vinculadas al cobre corresponden a polígonos asociados a cobre en la fuente OA.
- Los puntos COCHILCO representan localización de proyectos, no superficie.

## Contacto

Proyecto desarrollado por Gabriela Jerez.
