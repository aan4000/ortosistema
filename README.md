# OrtoSistema

Sistema de gestión para ortopedia y traumatología: pacientes, expediente, procedimientos, imágenes médicas con visor, documentos, facturación con catálogo de procedimientos, usuarios y roles.

La aplicación funciona **contra la API** (FastAPI + PostgreSQL/Neon). El navegador ya no guarda pacientes ni registros en `localStorage`: solo conserva el token de la sesión.

## Contenido

| Carpeta | Qué es |
|---|---|
| `frontend/index.html` | La aplicación completa en un solo archivo (HTML, CSS y JavaScript). La sirve el backend en `/`. |
| `backend/` | API en Python (FastAPI): login JWT, roles y permisos en el servidor, auditoría, datos, imágenes y documentos. |
| `database/schema.sql` | Esquema de PostgreSQL. El backend lo aplica al arrancar (`AUTO_SCHEMA=1`). |
| `render.yaml` | Blueprint de despliegue en Render. |

## Estado actual

- Frontend conectado a la API: login, registro inicial del administrador, pacientes, evaluaciones, procedimientos, quirófano, estudios con imágenes, documentos, facturación, usuarios y funciones por rol.
- Base de datos en **Neon** (`ortosistema`) con el esquema aplicado.
- Repositorio: <https://github.com/aan4000/ortosistema>.
- Despliegue en Render: pendiente de crear el servicio con la clave de API (ver más abajo).

## Probar en local

Requisitos: Python 3.12+ y una base PostgreSQL (Neon).

```powershell
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
Copy-Item .env.example .env    # completa DATABASE_URL y JWT_SECRET
```

Carga las variables y arranca:

```powershell
Get-Content .env | Where-Object { $_ -match '=' -and $_ -notmatch '^#' } | ForEach-Object {
  $k, $v = $_ -split '=', 2; Set-Item "env:$k" $v
}
.\.venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 3111
```

Abre <http://127.0.0.1:3111/>. La primera vez pide **crear la cuenta de administrador**; después ese administrador crea las demás cuentas y define qué secciones usa cada rol.

También puedes arrancar con `python main.py` (puerto 3000) o crear un usuario por consola:

```powershell
.\.venv\Scripts\python main.py crear-usuario dr.lopez medico "Dr. López"
```

## Despliegue en Render

El `render.yaml` define un servicio web gratuito en Oregon:

- Build: `pip install -r backend/requirements.txt`
- Start: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
- Salud: `/api/salud`
- Variables: `DATABASE_URL` (cadena de Neon, no se versiona) y `JWT_SECRET` (Render lo genera).

Pasos:

1. En Render, **New → Blueprint** y elige el repositorio `aan4000/ortosistema`.
2. Pega el valor de `DATABASE_URL` de Neon cuando lo pida.
3. Espera el despliegue y abre `https://ortosistema.onrender.com/`.
4. Crea el administrador en ese primer acceso.

El plan gratuito de Render duerme el servicio tras un rato sin uso; la primera visita puede tardar unos segundos. La base de datos está en Neon, así que los datos no se pierden cuando Render se duerme.

## Antes de usar datos reales de pacientes

- Usa HTTPS y un `JWT_SECRET` largo y aleatorio.
- No guardes contraseñas ni la cadena de la base de datos en el código ni en enlaces.
- Activa las copias de seguridad en Neon.
- Los precios del catálogo vienen en "Por definir": carga los aprobados por tu fuente (SDOT, aseguradora o tarifa propia).

Más detalle de endpoints y permisos en [`backend/README.md`](backend/README.md).
