# Diccionario de datos

## matriz_mineria_comunal_v1.csv

- `codreg`: código regional
- `codcom`: código comunal
- `nomreg`: nombre de la región
- `nomcom`: nombre de la comuna
- `superficie_comunal_ha`: superficie comunal de referencia
- `oa_ha`: superficie OA
- `concesiones_constituidas_ha`: superficie de concesiones constituidas
- `oa_concesiones_overlap_ha`: intersección OA y concesiones
- `oa_solo_ha`: superficie solo OA
- `concesiones_solo_ha`: superficie solo concesiones
- `union_total_ha`: cobertura integrada sin doble conteo
- `union_total_pct`: porcentaje de cobertura integrada
- `cochilco_n`: número de proyectos COCHILCO
- `cochilco_cobre_n`: número de proyectos COCHILCO de cobre

## matriz_cobre_comunal_v1.csv

- `cobre_exclusivo_ha`: superficie OA clasificada exclusivamente como cobre
- `cobre_asociado_ha`: superficie OA donde cobre aparece con otros minerales
- `cobre_total_ha`: superficie total asociada al cobre
- `cobre_pct_comunal`: porcentaje de superficie comunal asociado al cobre
- `cobre_pct_oa`: porcentaje del área OA comunal asociado al cobre
- `cobre_clases_overlap_ha`: superposición entre cobre exclusivo y cobre asociado

## Observaciones

- Valores nulos en `cobre_pct_oa` indican comunas sin superficie OA.
- Los indicadores COCHILCO se basan en asignación territorial de puntos.
