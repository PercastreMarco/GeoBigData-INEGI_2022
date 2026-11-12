# Diseño del esquema en MongoDB Atlas

Documento de diseño del esquema para el proyecto **GeoBigData-INEGI_2022** (réplica local del análisis de SCINCE 2020 y DENUE mayo 2022, con almacenamiento en MongoDB Atlas).

Se apoya en el material del Diplomado (IIMAS-UNAM): Módulo 5 (fundamentos y patrones de diseño) y Módulo 6 (Notas 02 a 06: agregación, indexación, validación, geoespacial y series de tiempo). Las referencias aparecen entre paréntesis, por ejemplo *(M6-N05)* = Módulo 6, Nota 05.

---

## 1. Decisiones de diseño

| # | Decisión | Justificación |
|---|----------|---------------|
| 1 | **Esquema analítico por lotes** (escritura por cargas ETL, lectura por agregaciones). Los datos crudos son inmutables y los resultados derivados se guardan aparte, por corrida. | "Model for your queries" *(M5)*. Un cambio de k, de giro o de radio no debe pisar resultados previos. |
| 2 | **Un solo corte de datos por base de datos** (SCINCE 2020 y DENUE 2022-05). `_id` de la manzana = `CVEGEO`. | Los datos son cortes puntuales, no series de tiempo *(M6-N06)*. El `CVEGEO` ya incluye la clave de entidad, por lo que el mismo `_id` sirve si luego se cargan más estados. |
| 3 | **Jerarquía SCIAN desnormalizada** (`sector`, `rama`, `clase`) dentro de cada negocio. | Los valores son estables y pocos; evita `$lookup` *(M6-N02)*. |
| 4 | **Frontera de almacenamiento:** solo Aguascalientes, solo las variables del análisis, y los Parquet originales se quedan locales (`data/raw/`, fuera de git). | Evita documentos inflados y respeta los 512 MB de M0 *(M5)*. |
| 5 | **Generalizable desde el inicio en el esquema y el `config.yaml`**; la lógica multi-estado queda para la Fase 2. | El esquema es lo caro de cambiar después; el config es barato. |

---

## 2. Colecciones

Base de datos: `geobigdata_inegi`. Nombres de campo en español y sin acentos, como en el curso.

### 2.1 `manzanas_scince` (datos crudos, inmutables)

```json
{
  "_id": "0100100010001001",
  "entidad": { "clave": "01" },
  "variables": {
    "ECO1_R": 120,
    "EDU46_R": 35,
    "VIV82_R": 80,
    "VIV83_R": 41,
    "VIV84_R": 12
  },
  "fuente": { "nombre": "SCINCE 2020", "anio": 2020 },
  "geometria": { "type": "Polygon", "coordinates": [[[-102.29, 21.88], "..."]] }
}
```

- `_id` = `CVEGEO` (clave natural, inmutable, permite *upsert* idempotente en el ETL).
- `variables` guarda los valores **ya limpios** (nulo o negativo pasa a 0, igual que la celda 26 del notebook). Las claves son los códigos originales de INEGI; los alias legibles viven en `config.yaml`.
- `geometria` es GeoJSON en WGS84, orden `[longitud, latitud]` *(M6-N05)*. Se reproyecta desde LCC (EPSG:6372) **antes** de cargar.
- Patrón: **Embedding** (1:1 con la manzana, se consulta siempre junto).

### 2.2 `denue_negocios` (datos crudos, inmutables)

```json
{
  "_id": "<identificador de la unidad económica del DENUE>",
  "entidad": { "clave": "01" },
  "actividad": { "sector": "46", "rama": "464", "clase": "464111" },
  "fuente": { "nombre": "DENUE", "corte": "2022-05-01T00:00:00Z" },
  "geometria": { "type": "Point", "coordinates": [-102.30, 21.88] }
}
```

- `_id`: se usará el identificador oficial de la unidad económica **si existe en el Parquet**. Pendiente de confirmar al inspeccionar las columnas. Si no existe, se calculará una clave determinista a partir de campos estables para conservar el *upsert* idempotente.
- `actividad.clase` es el `codigo_act` del notebook (6 dígitos); `sector` y `rama` son sus prefijos de 2 y 3 dígitos.
- `fuente.corte` es un valor `Date` (convención: primer día del mes), no una cadena *(M6-N04, M6-N06)*.
- Se cargan **todos** los negocios de Aguascalientes, no solo farmacias, para poder cambiar de giro en la Fase 2 sin recargar.

### 2.3 `corridas` (una por configuración ejecutada)

```json
{
  "_id": "01_k5_464111-464112_r1500",
  "creada_en": "2026-11-11T07:00:00Z",
  "config": {
    "estado": "01_AGS",
    "variables": ["ECO1_R", "EDU46_R", "VIV82_R", "VIV83_R", "VIV84_R"],
    "k_clusters": 5,
    "semilla": 1,
    "max_iter": 250,
    "codigo_actividad_interes": ["464111", "464112"],
    "nombre_amenidad": "Farmacias",
    "radio_buffer_metros": 1500
  }
}
```

Es la instantánea del `config.yaml` usado. Hace reproducible cada resultado y permite comparar corridas.

### 2.4 `resultados_manzanas` (derivados, por corrida)

```json
{
  "_id": "01_k5_464111-464112_r1500|0100100010001001",
  "corrida_id": "01_k5_464111-464112_r1500",
  "cvegeo": "0100100010001001",
  "features": { "ECO1_R": 120, "EDU46_R": 35, "VIV82_R": 80, "VIV83_R": 41, "VIV84_R": 12 },
  "cluster": 3,
  "n_amenidad": 2
}
```

- Separar lo derivado de lo crudo evita que una corrida pise a otra (anti-patrón de acoplar el documento a una sola configuración).
- `features` es el vector **usado en esa corrida** (Patrón **Subset/Computed**): permite calcular medias por cluster con un solo `$group`, **sin `$lookup`** *(M6-N02)*.
- `n_amenidad` es un **conteo**, no una tasa: las manzanas varían de tamaño y no hay medida de exposición *(M6-N06)*.
- `_id` compuesto como cadena `corrida|cvegeo`, en el mismo estilo que `exposicion_mensual` del curso *(M6-N06)*.

### 2.5 `resultados_clusters` (resumen por corrida, patrón Computed)

```json
{
  "_id": "01_k5_464111-464112_r1500|3",
  "corrida_id": "01_k5_464111-464112_r1500",
  "cluster": 3,
  "conteo": 1840,
  "medias": { "ECO1_R": 95.2, "EDU46_R": 28.1, "VIV82_R": 70.3, "VIV83_R": 33.0, "VIV84_R": 9.4 }
}
```

Es el equivalente de la celda 30 del notebook (medias y conteo por cluster). Se puede recalcular siempre desde `resultados_manzanas`.

### 2.6 Cardinalidades

| Relación | Cardinalidad | Tratamiento |
|----------|--------------|-------------|
| Manzana → variables | 1:1 | Embedding |
| Manzana → geometría | 1:1 | Embedding |
| Negocio → clasificación SCIAN | 1:1 | Embedding desnormalizado |
| Corrida → resultados por manzana | 1:muchos (~decenas de miles) | **Referencia** (colección aparte), no arreglo embebido (evita arreglos masivos) |
| Corrida → resumen por cluster | 1:pocos (k) | Colección aparte, un documento por cluster |

---

## 3. Índices

Cada índice se justifica con un patrón de consulta y se verifica con `explain("executionStats")` comparando `totalKeysExamined` y `totalDocsExamined` contra `nReturned`, antes y después *(M6-N03)*. No se crean índices "por si acaso": en M0 cada uno consume parte de los 512 MB.

| Colección | Índice | Patrón que atiende | Regla |
|-----------|--------|--------------------|-------|
| `denue_negocios` | `{ "actividad.clase": 1, geometria: "2dsphere" }` (`clase_geo`) | Negocios de una clase dentro de una zona o cerca de un punto | ESR: igualdad primero, luego el campo espacial *(M6-N03, M6-N05)*. Reemplaza dos índices separados |
| `manzanas_scince` | `{ geometria: "2dsphere" }` (`geometria_2dsphere`) | Verificación con `$geoIntersects` (sección 6.2) | Se crea solo si la verificación lo justifica por `explain`; se mide su tamaño |
| `resultados_manzanas` | `{ corrida_id: 1, cluster: 1 }` | `$match` por corrida y `$group` por cluster | Igualdad y luego agrupación |
| `resultados_clusters` | `{ corrida_id: 1, cluster: 1 }` | Lectura del resumen de una corrida | Igualdad |

Si el índice geoespacial no puede construirse, hay una geometría mal formada *(M6-N05)*: el error de la construcción es parte de la validación.

---

## 4. Validación de esquema (`$jsonSchema`)

Todas las colecciones usan `validationLevel: "strict"` y `validationAction: "error"`, porque se crean vacías y el ETL es el único escritor *(M6-N04)*. Las reglas se limitan a lo que necesita el modelo: estructura, tipos y dominios claros.

### 4.1 `manzanas_scince`

```python
validador_manzanas = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["_id", "entidad", "variables", "fuente", "geometria"],
        "properties": {
            "_id": {"bsonType": "string"},
            "entidad": {
                "bsonType": "object",
                "required": ["clave"],
                "properties": {"clave": {"bsonType": "string"}},
            },
            "variables": {
                "bsonType": "object",
                "patternProperties": {
                    "^[A-Z0-9_]+$": {
                        "bsonType": ["int", "long", "double", "decimal"],
                        "minimum": 0,
                    }
                },
                "additionalProperties": False,
            },
            "fuente": {
                "bsonType": "object",
                "required": ["nombre", "anio"],
                "properties": {
                    "nombre": {"bsonType": "string"},
                    "anio": {"bsonType": ["int", "long"]},
                },
            },
            "geometria": {
                "bsonType": "object",
                "required": ["type", "coordinates"],
                "properties": {
                    "type": {"enum": ["Polygon", "MultiPolygon"]},
                    "coordinates": {"bsonType": "array", "minItems": 1},
                },
            },
        },
    }
}
```

`patternProperties` permite cambiar de variables sin tocar el esquema, que es lo que hace posible la generalización.

### 4.2 `denue_negocios`

```python
validador_denue = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["_id", "entidad", "actividad", "fuente", "geometria"],
        "properties": {
            "_id": {"bsonType": "string"},
            "entidad": {
                "bsonType": "object",
                "required": ["clave"],
                "properties": {"clave": {"bsonType": "string"}},
            },
            "actividad": {
                "bsonType": "object",
                "required": ["sector", "rama", "clase"],
                "properties": {
                    "sector": {"bsonType": "string", "minLength": 2, "maxLength": 2},
                    "rama": {"bsonType": "string", "minLength": 3, "maxLength": 3},
                    "clase": {"bsonType": "string", "minLength": 6, "maxLength": 6},
                },
            },
            "fuente": {
                "bsonType": "object",
                "required": ["nombre", "corte"],
                "properties": {
                    "nombre": {"bsonType": "string"},
                    "corte": {"bsonType": "date"},
                },
            },
            "geometria": {
                "bsonType": "object",
                "required": ["type", "coordinates"],
                "properties": {
                    "type": {"enum": ["Point"]},
                    "coordinates": {
                        "bsonType": "array",
                        "minItems": 2,
                        "maxItems": 2,
                        "items": {"bsonType": ["double", "int"]},
                    },
                },
            },
        },
    }
}
```

### 4.3 Colecciones de corridas y resultados

- `corridas`: requeridos `_id`, `creada_en` (`date`) y `config` (objeto con `variables` arreglo con `minItems: 1`, `k_clusters` entero con `minimum: 2`, `radio_buffer_metros` con `minimum: 0`).
- `resultados_manzanas`: requeridos `corrida_id`, `cvegeo`, `features`, `cluster` (entero, `minimum: 0`) y `n_amenidad` (entero, `minimum: 0`).
- `resultados_clusters`: requeridos `corrida_id`, `cluster` (entero, `minimum: 0`), `conteo` (entero, `minimum: 0`) y `medias`.

### 4.4 Lo que `$jsonSchema` no cubre

El validador comprueba forma y tipos; **no** comprueba cierre de anillos, rangos de coordenadas por posición ni plausibilidad del dominio *(M6-N05)*. Eso se hace en un paso previo a la carga (sección 5).

### 4.5 Pruebas con documentos válidos e inválidos

Cada regla se prueba aislada, con una sola variación por caso *(M6-N04)*:

| Caso | Variación | Resultado esperado |
|------|-----------|--------------------|
| Documento completo | cumple tipos, presencia y rangos | aceptado |
| Campo obligatorio ausente | omite `geometria` | rechazado |
| Tipo incorrecto | `fuente.corte` como cadena | rechazado |
| Valor fuera de dominio | una variable con valor negativo | rechazado |
| Variable con nombre inválido | clave en minúsculas en `variables` | rechazado |
| Clase SCIAN mal formada | `clase` de 5 dígitos | rechazado |
| Geometría de tipo inválido | `type: "LineString"` | rechazado |

---

## 5. Validación geoespacial previa a la carga

Lista mínima antes de indexar *(M6-N05)*, implementada como función en el ETL:

1. Identificar el sistema de referencia de la fuente (LCC, EPSG:6372).
2. Transformar a WGS84 (EPSG:4326) antes de almacenar.
3. Conservar el orden `[longitud, latitud]`.
4. Comprobar estructura, tipos e intervalos (−180 ≤ lon ≤ 180, −90 ≤ lat ≤ 90).
5. Verificar que cada anillo cierre (primera posición igual a la última) y que cada polígono sea válido.
6. Dominio: las coordenadas deben caer dentro del rectángulo envolvente plausible de Aguascalientes. Esto detecta coordenadas invertidas o sin reproyectar.
7. Casos de prueba conocidos: puntos dentro, fuera y junto al límite.

Los documentos que no pasen se registran en un archivo de rechazos y no se cargan.

---

## 6. Consultas de verificación

### 6.1 Medias y conteo por cluster (contra `clusters.show()` de Spark)

```javascript
db.resultados_manzanas.aggregate([
  { $match: { corrida_id: "01_k5_464111-464112_r1500" } },
  { $group: {
      _id: "$cluster",
      conteo: { $sum: 1 },
      ECO1_R: { $avg: "$features.ECO1_R" },
      EDU46_R: { $avg: "$features.EDU46_R" },
      VIV82_R: { $avg: "$features.VIV82_R" },
      VIV83_R: { $avg: "$features.VIV83_R" },
      VIV84_R: { $avg: "$features.VIV84_R" }
  } },
  { $sort: { _id: 1 } }
])
```

Se construye etapa por etapa, anotando qué representa cada documento después de cada una *(M6-N02)*.

### 6.2 Verificación del join espacial de farmacias

El notebook usa `ST_Intersects(manzana, ST_Buffer(negocio, 1500))`. **MongoDB no tiene buffer**, y `$centerSphere` solo existe para `$geoWithin` (contención total, no intersección), por lo que el join masivo no se reproduce exacto en una sola consulta. Por eso `n_amenidad` se calcula en Spark o GeoPandas, como en el notebook.

MongoDB sirve para **verificar una muestra**: se construye el buffer de 1500 m de una farmacia en GeoPandas, se reproyecta a WGS84 y se consulta:

```javascript
db.manzanas_scince.find(
  { geometria: { $geoIntersects: { $geometry: bufferFarmacia } } },
  { _id: 1 }
)
```

El conjunto de `_id` devuelto debe coincidir con las manzanas que Spark asignó a esa farmacia. Se esperan diferencias solo en manzanas pegadas al límite del buffer, porque el buffer del notebook es plano sobre LCC y MongoDB interpreta los bordes sobre la esfera *(M6-N05, "casos de borde")*.

### 6.3 Negocios cercanos (`$geoNear`, primera etapa del pipeline)

```javascript
db.denue_negocios.aggregate([
  { $geoNear: {
      near: { type: "Point", coordinates: [-102.2915677, 21.8852562] },
      key: "geometria",
      distanceField: "distancia_metros",
      maxDistance: 1500,
      spherical: true,
      query: { "actividad.clase": { $in: ["464111", "464112"] } }
  } },
  { $limit: 10 }
])
```

La distancia es geoespacial en metros, no tiempo de traslado ni ruta vial *(M6-N05)*.

---

## 7. Capacidad en Atlas M0 (512 MB)

Fórmulas del curso *(M5)*: disco ≈ N × D × 1.5 × 0.3; conjunto de trabajo ≈ N × D × 0.2 + índices frecuentes; RAM ≈ × 1.5, con D medido por `Object.bsonsize()`.

**Pendiente:** el tamaño de las geometrías de las manzanas es la incógnita principal. Plan:

1. Cargar una muestra (~1000 manzanas y ~1000 negocios).
2. Medir `Object.bsonsize()` por documento y el tamaño de los índices.
3. Extrapolar a Aguascalientes completo y comparar contra los 512 MB.

Si no cabe con holgura: simplificar polígonos (con tolerancia documentada) o pasar a un clúster de pago. El resultado se registrará en este documento.

---

## 8. Interpretación y límites

Siguiendo las preguntas de interpretación de *(M6-N05)* y *(M6-N06)*:

- `n_amenidad` es un **conteo de farmacias a menos de 1500 m de la manzana** (la manzana intersecta el buffer). No es una tasa ni una medida de acceso real: no considera horarios, rutas ni capacidad.
- Los clusters describen similitud en las cinco variables; no demuestran causalidad.
- Una manzana puede quedar contada por varias farmacias cuando los buffers se traslapan; es consecuencia del modelo territorial, no un error.
- La distancia de la verificación en Mongo es esférica; la del notebook es plana sobre LCC.

---

## 9. Fuera de alcance de este documento

- Código del ETL (Fase 1, siguiente paso).
- Lógica multi-estado, descarga automática y CLI (Fase 2).
- Usuario de solo lectura para visualización (mínimo privilegio): pendiente en Atlas.
- Atlas M0 no ofrece respaldo ni cifrado a nivel de campo; los datos son públicos, pero conviene conservar los Parquet locales como fuente de recarga.