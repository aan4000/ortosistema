# OrtoSistema

Sistema de gestión para ortopedia y traumatología: pacientes, expediente, procedimientos, imágenes médicas con visor, documentos, facturación con catálogo de procedimientos, usuarios y roles.

## Contenido

| Carpeta | Qué es |
|---|---|
| `frontend/index.html` | La aplicación completa en un solo archivo (HTML, CSS y JavaScript). Ábrela con doble clic en Chrome, Edge o Safari. |
| `backend/` | API en Python (FastAPI) con login, roles, permisos, auditoría y endpoints de datos, imágenes y documentos. |
| `database/schema.sql` | Esquema de PostgreSQL (Neon u otro). El backend lo aplica al arrancar. |

## Estado actual

- **El front-end funciona solo, sin servidor.** Guarda usuarios, pacientes y registros en tu navegador (localStorage), y las imágenes y documentos en IndexedDB. Es ideal para probar, pero los datos no salen de ese navegador.
- **El backend está listo, pero el front-end todavía no lo usa.** Falta cambiar el front-end para que lea y escriba por la API (`/api/login`, `/api/datos`, `/api/paciente/{id}`, `/api/guardar`, etc.).
- **No incluye un backend en Node.js.** Si ya tienes uno propio (`server.js`), esta API en Python es una alternativa con el mismo tipo de base de datos.

## Probar el front-end

Abre `frontend/index.html`. La primera vez pide crear la cuenta de administrador. Desde ahí creas usuarios y eliges qué secciones usa cada rol.

## Arrancar el backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env     # completa DATABASE_URL (Neon) y JWT_SECRET
export $(grep -v '^#' .env | xargs)                 # Windows: define las variables a mano
python main.py           # http://localhost:3000/docs
```

Al abrir `http://localhost:3000/` el servidor muestra el front-end de `../frontend`. En el primer uso, `POST /api/registro-inicial` crea el administrador, o puedes usar `python main.py crear-usuario usuario admin "Nombre"`.

Los detalles de endpoints, permisos y despliegue en Render están en `backend/README.md`.

## Antes de usar datos reales de pacientes

- Cambia el `JWT_SECRET` por un texto largo y aleatorio, y usa siempre HTTPS.
- No guardes contraseñas ni la cadena de la base de datos en el código ni en enlaces.
- Activa las copias de seguridad en tu base de datos.
- Los precios del catálogo vienen en "Por definir": carga los aprobados por tu fuente (SDOT, aseguradora o tarifa propia).
