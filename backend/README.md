# OrtoSistema: backend en Python

FastAPI + PostgreSQL (Neon). Login con JWT, permisos por rol aplicados en el servidor, auditoría de accesos y cambios. El mismo servidor sirve el frontend de `../frontend`.

## Puesta en marcha

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # completa DATABASE_URL y JWT_SECRET
export $(grep -v '^#' .env | xargs)                 # Windows: define las variables a mano
python main.py crear-usuario dr.nombre medico "Dr. Nombre"   # pide la contraseña
python main.py                                      # http://localhost:3000/
```

Roles: `admin`, `medico`, `secretaria`, `fisio`.

El esquema de `../database/schema.sql` se aplica al arrancar si `AUTO_SCHEMA=1` (por defecto).

## Endpoints

| Método | Ruta | Uso |
|---|---|---|
| POST | `/api/login` | `{usuario, password}` → `{token, rol, nombre}` |
| GET | `/api/yo` | Usuario, rol y módulos de la sesión |
| GET | `/api/salud` | Comprobación de vida (despierta Render) |
| GET | `/api/estado` | `{requiere_registro}`: si falta crear el administrador |
| POST | `/api/registro-inicial` | `{usuario, nombre, password}`: crea el primer administrador |
| GET | `/api/todo` | Todas las tablas legibles por el rol, en una sola llamada |
| GET | `/api/datos` | Sin `tabla`: conteos. Con `tabla`, `q`, `pagina`, `limite`: registros |
| GET | `/api/medicos` | Nombres de médicos activos para los selectores |
| GET | `/api/paciente/{id}` | Expediente completo según el rol |
| POST | `/api/guardar` | `{tabla, datos, id?}`: crea o edita |
| DELETE | `/api/datos/{tabla}/{id}` | Elimina un registro (las tablas hijas caen en cascada) |
| GET | `/api/buscar?q=` | Búsqueda de pacientes |
| GET | `/api/dashboard` | Indicadores del rol en una llamada |

El primer administrador se crea desde la pantalla inicial (`POST /api/registro-inicial`), que solo funciona mientras no exista ningún usuario; después, el administrador crea las demás cuentas. La línea de comandos `python main.py crear-usuario` sigue disponible.

Solo administrador:

| Método | Ruta | Uso |
|---|---|---|
| GET / POST | `/api/usuarios` | Listar y crear usuarios (contraseña de 10+ caracteres) |
| PATCH | `/api/usuarios/{id}` | Cambiar nombre, rol, estado o contraseña. Siempre queda un administrador activo |
| GET / PUT | `/api/funciones` | Ver y cambiar las funciones de cada rol: `{rol, modulos:[...]}` |

`/api/yo` devuelve la lista de `modulos` del usuario para armar el menú. Los cambios de funciones, rol o estado se aplican en la siguiente llamada. Si corres varios procesos, reinícialos tras cambiar funciones (se guardan en memoria).

Todas, salvo login, salud y estado, piden `Authorization: Bearer <token>`.

## Frontend

1. El servidor sirve en `/` la carpeta `../frontend` (o `static/` junto a `main.py`, si existe).
2. Si el frontend vive en otro dominio, agrégalo a `CORS_ORIGINS`.
3. El frontend guarda el token en `localStorage` (solo la sesión) y lo envía en cada llamada. Los datos siempre viven en PostgreSQL.

## Despliegue en Render

- Build: `pip install -r backend/requirements.txt`
- Start: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
- Variables: `DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS` (opcional), `AUTO_SCHEMA=1`.

## Antes de usar datos reales

- `../database/schema.sql` solo crea tablas y columnas que falten. El diccionario `TABLAS` de `main.py` es la única lista de tablas y columnas permitidas.
- Usa HTTPS y un `JWT_SECRET` largo. No pongas credenciales en la URL.
- Activa las copias de seguridad en Neon.

## Catálogo de procedimientos (tarifario)

La tabla `tarifario` (`codigo`, `nombre`, `categoria`, `fuente`, `precio`) se lee y escribe con `/api/guardar` y `/api/datos?tabla=tarifario`. Al primer acceso del administrador se siembra un catálogo base con precios en 0 para que los completes. Cada cargo de `cargos_facturacion` guarda además el `medico` responsable.

## Imágenes médicas y procedimientos

- `POST /api/imagenes` recibe `{estudio_id, mime, datos_base64}` (JPG, PNG o WebP, hasta 8 MB) y `GET /api/imagenes/{id}` devuelve la imagen. Una etiqueta `<img>` no envía el token, así que el frontend la pide con `fetch` y el encabezado `Authorization`, y muestra el resultado como `blob:` en el visor.
- La miniatura del estudio se guarda en `estudios_imagenes.miniatura` y la imagen completa en `imagenes_estudio`.
- Los procedimientos asignados a cada paciente van en `procedimientos_paciente`, y el catálogo en `tarifario`.

## Paciente activo, verificación y documentos

- El paciente activo es una función del frontend: la API ya trabaja por paciente (`/api/paciente/{id}` y el filtro `paciente_id`).
- `POST /api/verificar` (`{tabla, id, verificado}`) marca un registro como verificado por el usuario. Editarlo con `/api/guardar` borra la verificación.
- Documentos: crea el registro con `/api/guardar` (tabla `documentos`), luego `PUT /api/documentos/{id}/archivo` sube el archivo en base64 (hasta 8 MB) y `GET` lo descarga.
