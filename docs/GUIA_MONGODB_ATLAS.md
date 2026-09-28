# Guía: creación del cluster MongoDB Atlas (M0 gratuito)

Esta guía documenta los pasos para crear el cluster que usará el proyecto `GeoBigData-INEGI_2022` como capa de almacenamiento. Al final tendrás un **connection string** listo para usar desde PySpark (Mongo Spark Connector) y desde scripts de Python (PyMongo).

## 1. Crear cuenta y organización

1. Entra a https://www.mongodb.com/cloud/atlas/register
2. Regístrate con tu correo (`percastremarco@gmail.com`) o con tu cuenta de GitHub/Google.
3. Al finalizar el registro, Atlas te pedirá crear una **Organización** y un **Proyecto**. Nombres sugeridos:
   - Organización: `Personal` o `PercastreMarco`
   - Proyecto: `GeoBigData-INEGI`

## 2. Crear el cluster M0 (gratuito)

1. Dentro del proyecto, clic en **"Build a Database"** (Crear una base de datos).
2. Selecciona el plan **M0 Free** (0 USD/mes, 512 MB de almacenamiento — suficiente para esta fase de réplica con un solo estado).
3. Configuración del cluster:
   - **Provider**: AWS (recomendado, mayor disponibilidad de regiones gratuitas).
   - **Región**: elige la más cercana a ti con tier gratuito disponible, por ejemplo `us-east-1` (N. Virginia) o `us-west-2` (Oregon). No hay región M0 en México, así que cualquiera de EE.UU. da buena latencia.
   - **Cluster Name**: `GeoBigDataCluster` (puedes cambiarlo, pero **no lo podrás renombrar después de creado**).
4. Clic en **"Create Deployment"**.

## 3. Configurar acceso: usuario de base de datos

Atlas te pedirá crear un usuario para autenticación (esto es independiente de tu login de Atlas).

1. **Authentication Method**: `Username and Password`.
2. **Username**: por ejemplo `geobigdata_app`.
3. **Password**: usa el botón **"Autogenerate Secure Password"** y **guárdala de inmediato** en un lugar seguro (gestor de contraseñas o `.env` local — nunca en el repo).
4. Clic en **"Create User"**.

> ⚠️ Importante: esta contraseña solo se muestra una vez. Si la pierdes, tendrás que regenerarla desde **Database Access**.

## 4. Configurar acceso de red (IP Access List)

Para conectar desde tu entorno local:

1. En la sección **"Where would you like to connect from?"**, Atlas sugiere agregar tu IP actual — acepta con **"Add My Current IP Address"**.
2. Si tu IP cambia frecuentemente (redes dinámicas, VPN, trabajas desde varios lugares), añade también `0.0.0.0/0` (permitir todas las IPs) en **Network Access → Add IP Address**.
   - Esto es aceptable para un cluster de desarrollo/práctica con datos públicos de INEGI, **no** para un cluster con datos sensibles o en producción.
3. Clic en **"Finish and Close"**.

## 5. Obtener el connection string

1. En el dashboard del proyecto, en tu cluster, clic en **"Connect"**.
2. Selecciona **"Drivers"** (para conectar desde una aplicación, que es nuestro caso con PyMongo/Spark).
3. Selecciona:
   - **Driver**: `Python`
   - **Version**: la más reciente listada (compatible con PyMongo 4.x).
4. Atlas te mostrará un string similar a:

```
mongodb+srv://geobigdata_app:<password>@geobigdatacluster.xxxxx.mongodb.net/?retryWrites=true&w=majority&appName=GeoBigDataCluster
```

5. Reemplaza `<password>` por la contraseña generada en el paso 3 (si tiene caracteres especiales como `@`, `#`, `%`, debes codificarlos en URL — ver sección 7).

## 6. Crear la base de datos y colecciones iniciales

No es necesario crear la base de datos manualmente — MongoDB la crea automáticamente en la primera escritura. Aun así, para tener nombres consistentes desde el inicio, el proyecto usará:

| Base de datos | Colección | Contenido |
|---|---|---|
| `geobigdata_inegi` | `manzanas_scince` | Manzanas censales con variables socioeconómicas (SCINCE), geometría en GeoJSON |
| `geobigdata_inegi` | `denue_negocios` | Negocios del DENUE, geometría de punto en GeoJSON |
| `geobigdata_inegi` | `resultados_clusters` | Salida del K-Means (fase de análisis) |

Estas colecciones se crearán automáticamente desde el script de ETL (siguiente fase del proyecto), junto con sus índices `2dsphere` para las consultas geoespaciales.

## 7. Guardar credenciales de forma segura (local)

En tu entorno local, crea un archivo `.env` (que **NO** se sube al repo — ya debe estar en `.gitignore`):

```bash
# .env
MONGODB_URI=mongodb+srv://geobigdata_app:TU_PASSWORD_CODIFICADA@geobigdatacluster.xxxxx.mongodb.net/?retryWrites=true&w=majority&appName=GeoBigDataCluster
MONGODB_DB=geobigdata_inegi
```

Si tu contraseña tiene caracteres especiales, codifícalos así (equivalencias comunes de URL-encoding):

| Carácter | Codificado |
|---|---|
| `@` | `%40` |
| `#` | `%23` |
| `%` | `%25` |
| `/` | `%2F` |
| `:` | `%3A` |

O más simple, en Python:
```python
from urllib.parse import quote_plus
password_codificada = quote_plus("tu_password_aqui")
```

## 8. Verificar la conexión

Con el cluster creado y el `.env` listo, instala el driver y prueba la conexión:

```bash
pip install pymongo python-dotenv
```

```python
import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

client = MongoClient(os.environ["MONGODB_URI"])
db = client[os.environ["MONGODB_DB"]]

# Ping de verificación
client.admin.command("ping")
print("✅ Conexión exitosa a MongoDB Atlas")
print("Bases de datos visibles:", client.list_database_names())
```

Si ves `✅ Conexión exitosa a MongoDB Atlas`, el cluster está listo para que empecemos con el script de ETL (PySpark → MongoDB Atlas).

## 9. Checklist final

- [ ] Cluster M0 creado y en estado **activo** (ícono verde en el dashboard).
- [ ] Usuario de base de datos creado, contraseña guardada de forma segura.
- [ ] IP Access List configurada (tu IP o `0.0.0.0/0` para desarrollo).
- [ ] Connection string probado con el script de verificación (paso 8).
- [ ] `.env` creado localmente y confirmado en `.gitignore` (no se sube a GitHub).

---

**Siguiente paso una vez completado este checklist**: preparar el conector Spark-MongoDB (`MongoDB Spark Connector`) para que PySpark pueda leer y escribir directamente en las colecciones de Atlas, y empezar el script de ETL (Fase 1: réplica exacta).