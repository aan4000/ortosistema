# OrtoSistema: backend en Python

FastAPI + PostgreSQL (Neon). Login con JWT, permisos por rol aplicados en el servidor, auditoría de accesos y cambios.

## Puesta en marcha

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # completa DATABASE_URL y JWT_SECRET
export $(grep -v '^#' .env | xargs)                 # Windows: define las variables a mano
python main.py crear-usuario dr.nombre medico "Dr. Nombre"   # pide la contraseña
python main.py                                      # http://localhost:3000/docs
```

Roles: `admin`, `medico`, `secretaria`, `fisio`.

## Endpoints

| Método | Ruta | Uso |
|---|---|---|
| POST | `/api/login` | `{usuario, password}` → `{token, rol, nombre}` |
| GET | `/api/yo` | Usuario de la sesión |
| GET | `/api/salud` | Comprobación de vida (despierta Render) |
| GET | `/api/datos` | Sin `tabla`: conteos. Con `tabla`, `q`, `pagina`, `limite`: registros |
| GET | `/api/paciente/{id}` | Expediente completo según el rol |
| POST | `/api/guardar` | `{tabla, datos, id?}`: crea o edita |
| GET | `/api/buscar?q=` | Búsqueda de pacientes |
| GET | `/api/dashboard` | Indicadores del rol en una llamada |

Primer uso: `GET /api/estado` dice si falta crear el administrador y `POST /api/registro-inicial` (`{usuario, nombre, password}`) lo crea. Solo funciona mientras no exista ningún usuario; después, el administrador crea las demás cuentas. La línea de comandos `python main.py crear-usuario` sigue disponible.

Solo administrador:

| Método | Ruta | Uso |
|---|---|---|
| GET / POST | `/api/usuarios` | Listar y crear usuarios (contraseña de 10+ caracteres) |
| PATCH | `/api/usuarios/{id}` | Cambiar nombre, rol, estado o contraseña. Siempre queda un administrador activo |
| GET / PUT | `/api/funciones` | Ver y cambiar las funciones de cada rol: `{rol, modulos:[...]}` |

`/api/yo` devuelve la lista de `modulos` del usuario para armar el menú. Los cambios de funciones, rol o estado se aplican en la siguiente llamada. Si corres varios procesos, reinícialos tras cambiar funciones (se guardan en memoria).

Todas, salvo login y salud, piden `Authorization: Bearer <token>`.

## Conectar el front-end

1. El servidor sirve en `/` la carpeta `../frontend` (o `static/` junto a `main.py`, si existe).
2. Si el front-end vive en otro dominio, agrégalo a `CORS_ORIGINS`.
3. Desde el front-end: `POST /api/login`, guarda el token y envíalo en cada llamada.

## Despliegue en Render

- Build: `pip install -r requirements.txt`
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Variables: `DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS`.

## Antes de usar datos reales

- `../database/schema.sql` solo crea tablas que no existan. Si tu base ya tiene tablas con otras columnas, ajusta el diccionario `TABLAS` de `main.py` (es la única lista de tablas y columnas permitidas) o migra con `alter table`.
- Usa HTTPS y un `JWT_SECRET` largo. No pongas credenciales en la URL.
- Activa las copias de seguridad en Neon.

## Catálogo de procedimientos (tarifario)

La tabla `tarifario` (`codigo`, `nombre`, `fuente`, `precio`) se lee y escribe con `/api/datos?tabla=tarifario` y `/api/guardar`. Carga ahí los precios aprobados por tu fuente (SDOT, aseguradora o tarifa propia). Cada cargo de `cargos_facturacion` guarda además el `medico` responsable.

## Imágenes médicas y procedimientos

- `POST /api/imagenes` recibe `{estudio_id, mime, datos_base64}` (JPG, PNG o WebP, hasta 8 MB) y `GET /api/imagenes/{id}` devuelve la imagen. Una etiqueta `<img>` no envía el token, así que el front-end la pide con `fetch` y el encabezado `Authorization`, y muestra el resultado como `blob:` en el visor.
- Los procedimientos asignados a cada paciente van en `procedimientos_paciente`, y el catálogo en `tarifario` (ahora con `categoria`).
- Si ya tenías el sistema en marcha, entra como administrador a **Administración → Funciones por rol** y activa **Procedimientos** para los roles que lo necesiten.

## Paciente activo, verificación y documentos

- El paciente activo es una función del front-end: la API ya trabaja por paciente (`/api/paciente/{id}` y el filtro `paciente_id`), así que no necesita cambios.
- `POST /api/verificar` (`{tabla, id, verificado}`) marca un registro como verificado por el usuario. Editarlo con `/api/guardar` borra la verificación.
- Documentos: crea el registro con `/api/guardar` (tabla `documentos`), luego `PUT /api/documentos/{id}/archivo` sube el archivo en base64 (hasta 8 MB) y `GET` lo descarga. Para activar la sección, ve a **Administración → Funciones por rol**.
