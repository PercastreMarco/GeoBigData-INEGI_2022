# Arquitectura del proyecto: GeoBigData-INEGI_2022

## 1. Contexto

El notebook original (`GeoBigData_INEGI_2022.ipynb`) fue desarrollado en Google Colab y resuelve un problema de analítica geoespacial con datos abiertos de INEGI:

- **DENUE** (Directorio Estadístico Nacional de Unidades Económicas): ~5.5 millones de registros de negocios georreferenciados.
- **SCINCE** (Sistema para la Consulta de Información Censal): variables socioeconómicas a nivel manzana.

El flujo original combina Apache Spark + Apache Sedona (procesamiento y operaciones geoespaciales tipo `ST_Intersects`/`ST_Buffer`) con GeoPandas y Folium para visualización, todo dentro de una sesión efímera de Colab: los datos se descargan, procesan y se pierden al cerrar la sesión.

El objetivo de este repositorio es **replicar ese análisis en un entorno local, reproducible, con los datos persistidos en una base de datos en la nube (MongoDB Atlas)**, en lugar de depender de archivos temporales de Colab.

## 2. Decisión de arquitectura: modelo híbrido

Se evaluaron tres alternativas de arquitectura:

| Alternativa | Descripción |
|---|---|
| A. Spark puro + Mongo como disco | Se mantiene toda la lógica geoespacial en Spark/Sedona; Mongo solo almacena resultados planos. |
| B. Python puro (sin Spark) | pandas + geopandas + shapely + scikit-learn + PyMongo. |
| **C. Híbrida (elegida)** | PySpark para ETL y cómputo (K-Means), MongoDB Atlas para almacenamiento y consultas geoespaciales nativas. |

### 2.1 Por qué no la alternativa A (Spark + Mongo como disco plano)

Usar Mongo únicamente como reemplazo de los archivos parquet desaprovecha su capacidad geoespacial nativa (índices `2dsphere`, operadores `$geoNear`, `$geoIntersects`). Bajo ese esquema, los joins espaciales seguirían resolviéndose enteramente vía Sedona, y Mongo aportaría poco más que "un disco caro en la nube".

### 2.2 Por qué no la alternativa B (Python puro, sin Spark)

Es una opción válida y más simple de mantener — el volumen real de datos (DENUE ~1-2 GB, SCINCE de un estado en decenas de miles de manzanas) cabe perfectamente en memoria de una máquina local, por lo que Spark no es estrictamente necesario por volumen. Sin embargo:

- El notebook original y su nombre ("GeoBigData") están construidos explícitamente para demostrar dominio de Spark/Spark SQL.
- Se perdería la equivalencia directa con la lógica ya validada en el notebook (limpiezas con `if(isnull(...))`, `KMeans` de `pyspark.ml`), obligando a reescribir esa lógica en pandas/sklearn sin necesidad real.

### 2.3 Por qué la alternativa C (híbrida)

| Etapa | Herramienta | Justificación |
|---|---|---|
| **Ingesta / ETL** (leer parquet → limpiar → cargar) | **PySpark local** | Reutiliza la misma lógica de limpieza en Spark SQL ya validada en el notebook original; corre en paralelo aprovechando los cores de la máquina local. |
| **Almacenamiento** | **MongoDB Atlas** | Reemplaza los archivos parquet como fuente de verdad, persistente y reproducible en la nube. Los índices `2dsphere` permiten consultas geoespaciales nativas (`$geoNear`, `$geoIntersects`) que sustituyen directamente los `ST_Intersects`/`ST_Buffer` de Apache Sedona — sin necesidad de mantener esa dependencia. |
| **Análisis** (K-Means, agregaciones) | **PySpark**, leyendo desde Mongo vía **MongoDB Spark Connector** | Mismo motor de cómputo ya usado en el notebook (`pyspark.ml.clustering.KMeans`), pero ahora lee y escribe directo de Atlas. El pipeline queda 100% reproducible sin depender de tener los `.zip`/parquet originales en disco. |
| **Visualización** | **GeoPandas + Folium** | Sin cambios respecto al notebook original: no hay razón técnica para modificar esta etapa. |

**Resumen de la decisión**: se conserva Spark como motor de cómputo (ETL y K-Means) por continuidad con el análisis original y por ser el objetivo pedagógico del proyecto, y se introduce MongoDB Atlas no como simple almacenamiento sino como **reemplazo funcional de Apache Sedona** para las operaciones geoespaciales, aprovechando sus índices y operadores nativos.

## 3. Estrategia de implementación en dos fases

Para minimizar el riesgo de depurar dos problemas a la vez (lógica del pipeline + diseño de parametrización), la implementación se hace en dos fases secuenciales.

### Fase 1 — Réplica exacta (validación del pipeline)

Se implementa el flujo completo con los mismos valores fijos del notebook original:

```
Parquet (SCINCE/DENUE) → PySpark (limpieza)  → MongoDB Atlas (storage)
                                                       ↓
                           PySpark (lee vía Mongo Connector, K-Means k=5)
                                                       ↓
                           GeoPandas + Folium (mapas, caso: farmacias en Aguascalientes)
```

Parámetros fijos en esta fase:

- Estado: Aguascalientes (`01_AGS`).
- Variables SCINCE: las 5 usadas originalmente (económicas y de vivienda).
- Número de clusters: `k = 5`.
- Giro comercial de interés: farmacias (códigos SCIAN correspondientes).
- Radio de búsqueda: 1500 metros.

**Criterio de éxito de la Fase 1**: los resultados (clusters, mapa de densidad, cruces socioeconómicos) deben coincidir con los obtenidos en `GeoBigData_INEGI_2022.ipynb`. Solo al confirmar esta equivalencia se avanza a la Fase 2.

### Fase 2 — Generalización por configuración

Una vez validada la Fase 1, los valores fijos se extraen a un archivo de configuración (`config.yaml`), sin modificar la lógica interna de los scripts:

```yaml
estado: "01_AGS"
variables:
  - "ECO1_R"
  - "EDU46_R"
  - "VIV82_R"
  - "VIV83_R"
  - "VIV84_R"
k_clusters: 5
codigo_actividad_interes:
  - "464111"
  - "464112"
nombre_amenidad: "Farmacias"
radio_buffer_metros: 1500
```

Esto permite ejecutar el análisis para cualquier estado, conjunto de variables o giro comercial (por ejemplo, escuelas, bancos, gimnasios) sin tocar el código fuente, simplemente cambiando el archivo de configuración o pasándolo como argumento (`python run_analysis.py --config config_jalisco.yaml`).

## 4. Justificación del orden de las fases

Abordar primero la réplica exacta permite:

1. Aislar y resolver únicamente los problemas de migración (Spark local vs. Colab, conexión a Mongo Atlas, conector Spark-Mongo) sin mezclarlos con decisiones de diseño de parametrización.
2. Tener un punto de comparación objetivo: si los resultados no coinciden con el notebook original, el error está en la migración de infraestructura, no en un rediseño de la lógica.
3. Generalizar sobre una base ya probada, reduciendo el riesgo de construir una capa de configuración flexible sobre un pipeline que aún no se sabe si funciona correctamente.