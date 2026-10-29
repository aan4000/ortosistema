"""OrtoSistema: API en Python (FastAPI + PostgreSQL/Neon)."""
import datetime as dt
import getpass
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import bcrypt
import jwt
import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Request
import base64
from fastapi import Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

DATABASE_URL = os.environ["DATABASE_URL"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_HORAS = int(os.getenv("JWT_HORAS", "8"))
CORS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
AQUI = Path(__file__).parent

pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=5, open=False,
                      kwargs={"row_factory": dict_row})

# Tablas y columnas permitidas. Es la única lista que toca SQL dinámico:
# si una tabla o columna no está aquí, la API la rechaza.
TABLAS = {
    "pacientes": ["nombre", "edad", "cedula", "seguro", "alergias", "diagnostico", "etapa",
                  "antecedentes_morbidos", "antecedentes_quirurgicos", "medicamentos",
                  "antecedentes_familiares", "habitos", "fecha_nacimiento", "sexo", "telefono",
                  "correo", "direccion", "numero_afiliado", "tipo_sangre"],
    "citas": ["paciente_id", "fecha", "hora", "motivo"],
    "evaluaciones": ["paciente_id", "fecha", "texto"],
    "estudios_imagenes": ["paciente_id", "fecha", "tipo", "estado", "informe"],
    "cirugias": ["paciente_id", "fecha", "procedimiento", "estado"],
    "implantes": ["cirugia_id", "paciente_id", "descripcion", "lote"],
    "pt_sesiones": ["paciente_id", "fecha", "descripcion", "dolor"],
    "formularios_proms": ["paciente_id", "fecha", "cuestionario", "puntaje"],
    "referimientos": ["paciente_id", "fecha", "detalle", "estado"],
    "autorizaciones_preauth": ["paciente_id", "procedimiento", "seguro", "estado", "vence"],
    "cargos_facturacion": ["paciente_id", "fecha", "codigo", "concepto", "monto", "estado", "medico"],
    "tarifario": ["codigo", "nombre", "categoria", "fuente", "precio"],
    "procedimientos_paciente": ["paciente_id", "fecha", "procedimiento", "codigo", "categoria",
                                "precio", "medico", "estado"],
    "documentos": ["paciente_id", "nombre", "url", "tipo", "fecha"],
}
CLINICAS = {"pacientes", "citas", "evaluaciones", "estudios_imagenes", "cirugias", "implantes",
            "pt_sesiones", "formularios_proms", "referimientos", "documentos",
            "procedimientos_paciente"}
GESTION = {"pacientes", "citas", "referimientos", "autorizaciones_preauth",
           "cargos_facturacion", "tarifario", "documentos"}
PERMISOS = {  # los permisos se aplican aquí, en el servidor
    "admin": {"leer": "*", "escribir": "*"},
    "medico": {"leer": "*", "escribir": CLINICAS | {"autorizaciones_preauth"}},
    "secretaria": {"leer": GESTION, "escribir": GESTION},
    "fisio": {"leer": {"pacientes", "citas", "pt_sesiones", "formularios_proms"},
              "escribir": {"pt_sesiones", "formularios_proms"}},
}


MODULOS = {  # función del menú -> tablas que gobierna
    "agenda": ["citas"],
    "pacientes": ["pacientes", "evaluaciones", "documentos"],
    "quirofano": ["cirugias", "implantes"],
    "estudios": ["estudios_imagenes"],
    "rehab": ["pt_sesiones", "formularios_proms"],
    "referimientos": ["referimientos"],
    "autorizaciones": ["autorizaciones_preauth"],
    "procedimientos": ["procedimientos_paciente"],
    "facturacion": ["cargos_facturacion", "tarifario"],
}
TABLA_MODULO = {t: m for m, ts in MODULOS.items() for t in ts}
FUNC_INICIAL = {
    "medico": set(MODULOS),
    "secretaria": {"agenda", "pacientes", "referimientos", "autorizaciones", "facturacion"},
    "fisio": {"agenda", "pacientes", "rehab"},
}
FUNC: dict = {}  # rol -> funciones activas (el administrador siempre tiene todas)


def puede(rol, accion, tabla):
    if tabla not in TABLAS:
        return False
    if rol == "admin":
        return True
    p = PERMISOS.get(rol, {}).get(accion, set())
    return (p == "*" or tabla in p) and TABLA_MODULO.get(tabla) in FUNC.get(rol, set())


def cargar_funciones():
    with pool.connection() as c:
        filas = c.execute("select rol, modulo from funciones_rol").fetchall()
        if not any(f["rol"] == "_init" for f in filas):  # primera vez: valores por defecto
            for r, ms in FUNC_INICIAL.items():
                for mod in ms:
                    c.execute("insert into funciones_rol(rol,modulo) values (%s,%s) on conflict do nothing", (r, mod))
            c.execute("insert into funciones_rol(rol,modulo) values ('_init','_') on conflict do nothing")
            filas = c.execute("select rol, modulo from funciones_rol").fetchall()
    FUNC.clear()
    for f in filas:
        FUNC.setdefault(f["rol"], set()).add(f["modulo"])


def exigir(u, accion, tabla):
    if tabla not in TABLAS:
        raise HTTPException(404, "Tabla desconocida")
    if not puede(u["rol"], accion, tabla):
        raise HTTPException(403, "Tu rol no tiene permiso para esta acción")


def aplicar_schema():
    ruta = next(p for p in (AQUI / "schema.sql", AQUI.parent / "database" / "schema.sql") if p.exists())
    sql = ruta.read_text(encoding="utf-8")
    with pool.connection() as c:
        c.execute(sql)


@asynccontextmanager
async def ciclo(app):
    pool.open()
    if os.getenv("AUTO_SCHEMA", "1") == "1":
        aplicar_schema()
    cargar_funciones()
    yield
    pool.close()


app = FastAPI(title="OrtoSistema API", lifespan=ciclo)
if CORS:
    app.add_middleware(CORSMiddleware, allow_origins=CORS, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(psycopg.Error)
async def error_bd(_: Request, e: psycopg.Error):
    return JSONResponse({"detail": "Dato inválido o registro relacionado inexistente"}, 400)


# ---------- Autenticación ----------
bearer = HTTPBearer(auto_error=False)
INTENTOS: dict = {}  # (usuario, ip) -> (fallos, último_intento)


def usuario_actual(cred: HTTPAuthorizationCredentials = Depends(bearer)):
    if not cred:
        raise HTTPException(401, "Inicia sesión para continuar")
    try:
        u = jwt.decode(cred.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Tu sesión venció. Inicia sesión de nuevo")
    with pool.connection() as c:
        r = c.execute("select rol, activo from usuarios where usuario=%s", (u["sub"],)).fetchone()
    if not r or not r["activo"]:
        raise HTTPException(401, "Tu usuario está desactivado")
    u["rol"] = r["rol"]
    return u


def auditar(c, u, accion, tabla, registro=None):
    c.execute("insert into auditoria(usuario,accion,tabla,registro_id) values (%s,%s,%s,%s)",
              (u["sub"], accion, tabla, registro))


class Login(BaseModel):
    usuario: str
    password: str


@app.post("/api/login")
def login(d: Login, req: Request):
    k = (d.usuario.lower(), req.client.host if req.client else "")
    fallos, t = INTENTOS.get(k, (0, 0))
    if time.time() - t > 900:
        fallos = 0
    if fallos >= 5:
        raise HTTPException(429, "Demasiados intentos. Espera 15 minutos")
    with pool.connection() as c:
        u = c.execute("select * from usuarios where lower(usuario)=%s and activo",
                      (d.usuario.lower(),)).fetchone()
    if not u or not bcrypt.checkpw(d.password.encode(), u["password_hash"].encode()):
        INTENTOS[k] = (fallos + 1, time.time())
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    INTENTOS.pop(k, None)
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=JWT_HORAS)
    token = jwt.encode({"sub": u["usuario"], "rol": u["rol"], "nombre": u["nombre"], "exp": exp},
                       JWT_SECRET, algorithm="HS256")
    return {"token": token, "rol": u["rol"], "nombre": u["nombre"]}


@app.get("/api/yo")
def yo(u=Depends(usuario_actual)):
    return {"usuario": u["sub"], "rol": u["rol"], "nombre": u["nombre"],
            "modulos": sorted(MODULOS) if u["rol"] == "admin" else sorted(FUNC.get(u["rol"], set())),
            "es_admin": u["rol"] == "admin"}


@app.get("/api/salud")
def salud():
    with pool.connection() as c:
        c.execute("select 1")
    return {"ok": True}


# ---------- Verificación de registros y documentos ----------
VERIFICABLES = {"evaluaciones", "estudios_imagenes", "cirugias", "pt_sesiones", "formularios_proms",
                "referimientos", "autorizaciones_preauth", "procedimientos_paciente",
                "cargos_facturacion", "documentos"}


class Verificar(BaseModel):
    tabla: str
    id: int
    verificado: bool = True


@app.post("/api/verificar")
def verificar(d: Verificar, u=Depends(usuario_actual)):
    """Marca o desmarca un registro como verificado por el usuario. Editarlo borra la verificación."""
    exigir(u, "escribir", d.tabla)
    if d.tabla not in VERIFICABLES:
        raise HTTPException(400, "Esta tabla no se verifica")
    quien = u["sub"] if d.verificado else None
    cuando = dt.datetime.now(dt.timezone.utc) if d.verificado else None
    with pool.connection() as c:
        r = c.execute(f"update {d.tabla} set verificado_por=%s, verificado_en=%s where id=%s returning id",
                      (quien, cuando, d.id)).fetchone()
        if not r:
            raise HTTPException(404, "Registro no encontrado")
        auditar(c, u, "verificar" if d.verificado else "quitar-verificacion", d.tabla, d.id)
    return {"ok": True}


class Archivo(BaseModel):
    mime: str = "application/octet-stream"
    datos_base64: str


@app.put("/api/documentos/{did}/archivo")
def documento_subir(did: int, d: Archivo, u=Depends(usuario_actual)):
    """Adjunta el archivo (hasta 8 MB) a un documento ya creado con /api/guardar."""
    exigir(u, "escribir", "documentos")
    try:
        datos = base64.b64decode(d.datos_base64, validate=True)
    except ValueError:
        raise HTTPException(400, "Archivo inválido")
    if len(datos) > 8_000_000:
        raise HTTPException(413, "El archivo supera 8 MB")
    with pool.connection() as c:
        r = c.execute("update documentos set archivo=%s, mime=%s, tamano=%s, "
                      "verificado_por=null, verificado_en=null where id=%s returning id",
                      (datos, d.mime, len(datos), did)).fetchone()
        if not r:
            raise HTTPException(404, "Documento no encontrado")
        auditar(c, u, "subir-archivo", "documentos", did)
    return {"ok": True}


@app.get("/api/documentos/{did}/archivo")
def documento_bajar(did: int, u=Depends(usuario_actual)):
    exigir(u, "leer", "documentos")
    with pool.connection() as c:
        r = c.execute("select nombre,mime,archivo from documentos where id=%s", (did,)).fetchone()
        if not r or r["archivo"] is None:
            raise HTTPException(404, "Documento sin archivo")
        auditar(c, u, "descargar", "documentos", did)
    return Response(bytes(r["archivo"]), media_type=r["mime"] or "application/octet-stream",
                    headers={"Content-Disposition": 'attachment; filename="documento"'})


# ---------- Imágenes médicas ----------
class Imagen(BaseModel):
    estudio_id: int
    mime: str = "image/jpeg"
    datos_base64: str


@app.post("/api/imagenes")
def imagen_subir(d: Imagen, u=Depends(usuario_actual)):
    """Sube una imagen (JPG, PNG o WebP, hasta 8 MB) y la liga a un estudio."""
    exigir(u, "escribir", "estudios_imagenes")
    if d.mime not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(400, "Solo se aceptan imágenes JPG, PNG o WebP")
    try:
        datos = base64.b64decode(d.datos_base64, validate=True)
    except ValueError:
        raise HTTPException(400, "Imagen inválida")
    if len(datos) > 8_000_000:
        raise HTTPException(413, "La imagen supera 8 MB")
    with pool.connection() as c:
        r = c.execute("insert into imagenes_estudio(estudio_id,mime,datos) values (%s,%s,%s) returning id",
                      (d.estudio_id, d.mime, datos)).fetchone()
        auditar(c, u, "subir", "imagenes_estudio", r["id"])
    return {"ok": True, "id": r["id"]}


@app.get("/api/imagenes/{iid}")
def imagen_ver(iid: int, u=Depends(usuario_actual)):
    """Devuelve los bytes de la imagen. El front-end la pide con el token y crea un blob para el visor."""
    exigir(u, "leer", "estudios_imagenes")
    with pool.connection() as c:
        r = c.execute("select mime,datos from imagenes_estudio where id=%s", (iid,)).fetchone()
        if not r:
            raise HTTPException(404, "Imagen no encontrada")
        auditar(c, u, "ver", "imagenes_estudio", iid)
    return Response(bytes(r["datos"]), media_type=r["mime"])


# ---------- Primer uso: registro del administrador ----------
class RegistroInicial(BaseModel):
    usuario: str
    nombre: str
    password: str


@app.get("/api/estado")
def estado():
    """El front-end muestra la pantalla de registro cuando aún no existe ningún usuario."""
    with pool.connection() as c:
        n = c.execute("select count(*) n from usuarios").fetchone()["n"]
    return {"requiere_registro": n == 0}


@app.post("/api/registro-inicial")
def registro_inicial(d: RegistroInicial):
    """Crea el primer administrador. Solo funciona mientras no exista ningún usuario."""
    _validar("admin", d.password)
    h = bcrypt.hashpw(d.password.encode(), bcrypt.gensalt()).decode()
    with pool.connection() as c:
        r = c.execute("insert into usuarios(usuario,nombre,rol,password_hash) "
                      "select %s::text,%s::text,'admin',%s::text "
                      "where not exists (select 1 from usuarios) returning id",
                      (d.usuario.lower(), d.nombre, h)).fetchone()
        if not r:
            raise HTTPException(409, "El sistema ya tiene usuarios. Pide al administrador que te cree una cuenta")
        auditar(c, {"sub": d.usuario.lower()}, "registro-inicial", "usuarios", r["id"])
    return {"ok": True}


# ---------- Administración (solo rol admin) ----------
def solo_admin(u=Depends(usuario_actual)):
    if u["rol"] != "admin":
        raise HTTPException(403, "Solo el administrador puede hacer esto")
    return u


class NuevoUsuario(BaseModel):
    usuario: str
    nombre: str
    rol: str
    password: str


class CambioUsuario(BaseModel):
    nombre: str | None = None
    rol: str | None = None
    activo: bool | None = None
    password: str | None = None


def _validar(rol=None, password=None):
    if rol is not None and rol not in PERMISOS:
        raise HTTPException(400, "Rol inválido")
    if password is not None and len(password) < 10:
        raise HTTPException(400, "La contraseña debe tener al menos 10 caracteres")


@app.get("/api/usuarios")
def usuarios(u=Depends(solo_admin)):
    with pool.connection() as c:
        return {"usuarios": c.execute(
            "select id,usuario,nombre,rol,activo from usuarios order by usuario").fetchall()}


@app.post("/api/usuarios")
def usuario_nuevo(d: NuevoUsuario, u=Depends(solo_admin)):
    _validar(d.rol, d.password)
    h = bcrypt.hashpw(d.password.encode(), bcrypt.gensalt()).decode()
    with pool.connection() as c:
        if c.execute("select 1 from usuarios where lower(usuario)=%s", (d.usuario.lower(),)).fetchone():
            raise HTTPException(409, "Ese usuario ya existe")
        r = c.execute("insert into usuarios(usuario,nombre,rol,password_hash) values (%s,%s,%s,%s) returning id",
                      (d.usuario.lower(), d.nombre, d.rol, h)).fetchone()
        auditar(c, u, "crear", "usuarios", r["id"])
    return {"ok": True, "id": r["id"]}


@app.patch("/api/usuarios/{uid}")
def usuario_editar(uid: int, d: CambioUsuario, u=Depends(solo_admin)):
    _validar(d.rol, d.password)
    campos = {}
    if d.nombre is not None:
        campos["nombre"] = d.nombre
    if d.rol is not None:
        campos["rol"] = d.rol
    if d.activo is not None:
        campos["activo"] = d.activo
    if d.password is not None:
        campos["password_hash"] = bcrypt.hashpw(d.password.encode(), bcrypt.gensalt()).decode()
    if not campos:
        raise HTTPException(400, "Nada que cambiar")
    with pool.connection() as c:
        a = c.execute("select rol, activo from usuarios where id=%s", (uid,)).fetchone()
        if not a:
            raise HTTPException(404, "Usuario no encontrado")
        sigue_admin = (d.rol or a["rol"]) == "admin" and (a["activo"] if d.activo is None else d.activo)
        otros = c.execute("select count(*) n from usuarios where rol='admin' and activo and id<>%s",
                          (uid,)).fetchone()["n"]
        if not sigue_admin and not otros:
            raise HTTPException(400, "Debe quedar al menos un administrador activo")
        c.execute(f"update usuarios set {','.join(k + '=%s' for k in campos)} where id=%s",
                  list(campos.values()) + [uid])
        auditar(c, u, "editar", "usuarios", uid)
    return {"ok": True}


class Funciones(BaseModel):
    rol: str
    modulos: list[str]


@app.get("/api/funciones")
def funciones(u=Depends(solo_admin)):
    return {"modulos": list(MODULOS),
            "roles": {r: sorted(FUNC.get(r, set())) for r in PERMISOS if r != "admin"}}


@app.put("/api/funciones")
def funciones_guardar(d: Funciones, u=Depends(solo_admin)):
    """Agrega o quita funciones a un rol. Se aplica de inmediato a la API y al menú."""
    if d.rol not in PERMISOS or d.rol == "admin":
        raise HTTPException(400, "Rol inválido")
    if any(x not in MODULOS for x in d.modulos):
        raise HTTPException(400, "Función desconocida")
    with pool.connection() as c:
        c.execute("delete from funciones_rol where rol=%s", (d.rol,))
        for x in set(d.modulos):
            c.execute("insert into funciones_rol(rol,modulo) values (%s,%s)", (d.rol, x))
        auditar(c, u, "funciones", "funciones_rol")
    FUNC[d.rol] = set(d.modulos)
    return {"ok": True}


# ---------- Datos ----------
@app.get("/api/datos")
def datos(tabla: str | None = None, q: str = "", pagina: int = Query(1, ge=1),
          limite: int = Query(25, ge=1, le=100), u=Depends(usuario_actual)):
    """Sin `tabla`: conteos por tabla. Con `tabla`: página de registros (q filtra pacientes)."""
    with pool.connection() as c:
        if not tabla:
            return {"conteos": {t: c.execute(f"select count(*) n from {t}").fetchone()["n"]
                                for t in TABLAS if puede(u["rol"], "leer", t)}}
        exigir(u, "leer", tabla)
        where, args = "", []
        if q and tabla == "pacientes":
            where, args = " where nombre ilike %s or cedula ilike %s", [f"%{q}%"] * 2
        total = c.execute(f"select count(*) n from {tabla}{where}", args).fetchone()["n"]
        cols = ",".join(["id"] + TABLAS[tabla])
        filas = c.execute(f"select {cols} from {tabla}{where} order by id desc limit %s offset %s",
                          args + [limite, (pagina - 1) * limite]).fetchall()
    return {"tabla": tabla, "total": total, "pagina": pagina, "filas": filas}


@app.get("/api/paciente/{pid}")
def paciente(pid: int, u=Depends(usuario_actual)):
    """Expediente: el paciente y sus registros de las tablas que el rol puede leer."""
    exigir(u, "leer", "pacientes")
    with pool.connection() as c:
        p = c.execute(f"select id,{','.join(TABLAS['pacientes'])} from pacientes where id=%s",
                      (pid,)).fetchone()
        if not p:
            raise HTTPException(404, "Paciente no encontrado")
        rel = {t: c.execute(f"select id,{','.join(cols)} from {t} where paciente_id=%s order by id desc",
                            (pid,)).fetchall()
               for t, cols in TABLAS.items()
               if t != "pacientes" and "paciente_id" in cols and puede(u["rol"], "leer", t)}
        auditar(c, u, "ver", "pacientes", pid)
    return {"paciente": p, **rel}


class Guardar(BaseModel):
    tabla: str
    datos: dict
    id: int | None = None  # con id edita; sin id crea


@app.post("/api/guardar")
def guardar(g: Guardar, u=Depends(usuario_actual)):
    exigir(u, "escribir", g.tabla)
    cols = [k for k in g.datos if k in TABLAS[g.tabla]]
    if not cols:
        raise HTTPException(400, "No hay campos válidos para guardar")
    vals = [g.datos[k] for k in cols]
    with pool.connection() as c:
        if g.id:
            r = c.execute(f"update {g.tabla} set {','.join(k + '=%s' for k in cols)} "
                          f"{', verificado_por=null, verificado_en=null' if g.tabla in VERIFICABLES else ''} "
                          "where id=%s returning id", vals + [g.id]).fetchone()
            if not r:
                raise HTTPException(404, "Registro no encontrado")
            accion = "editar"
        else:
            r = c.execute(f"insert into {g.tabla}({','.join(cols)}) "
                          f"values ({','.join(['%s'] * len(cols))}) returning id", vals).fetchone()
            accion = "crear"
        auditar(c, u, accion, g.tabla, r["id"])
    return {"ok": True, "id": r["id"]}


@app.get("/api/buscar")
def buscar(q: str = Query(min_length=2), u=Depends(usuario_actual)):
    exigir(u, "leer", "pacientes")
    with pool.connection() as c:
        r = c.execute("select id,nombre,cedula,diagnostico from pacientes "
                      "where nombre ilike %s or cedula ilike %s order by nombre limit 10",
                      [f"%{q}%"] * 2).fetchall()
    return {"pacientes": r}


KPIS = {
    "citas_hoy": ("citas", "fecha = current_date"),
    "cirugias_programadas": ("cirugias", "estado = 'Programada'"),
    "estudios_por_revisar": ("estudios_imagenes", "estado = 'Por revisar'"),
    "proms_bajos": ("formularios_proms", "puntaje < 50"),
    "preauth_pendientes": ("autorizaciones_preauth", "estado in ('Por solicitar','Enviada')"),
    "cobros_pendientes": ("cargos_facturacion", "estado = 'Pendiente'"),
    "referimientos_sin_responder": ("referimientos", "estado = 'Pendiente'"),
}


@app.get("/api/dashboard")
def dashboard(u=Depends(usuario_actual)):
    """Todos los indicadores del rol en una sola llamada."""
    with pool.connection() as c:
        return {k: c.execute(f"select count(*) n from {t} where {w}").fetchone()["n"]
                for k, (t, w) in KPIS.items() if puede(u["rol"], "leer", t)}


# Sirve el front-end desde el mismo servidor: carpeta `static/` o, si no existe, `../frontend`.
WEB = next((p for p in (AQUI / "static", AQUI.parent / "frontend") if p.is_dir()), None)
if WEB:
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")


def crear_usuario(usuario, rol, nombre):
    if rol not in PERMISOS:
        sys.exit("Rol inválido. Usa: " + ", ".join(PERMISOS))
    clave = getpass.getpass("Contraseña (mínimo 10 caracteres): ")
    if len(clave) < 10:
        sys.exit("La contraseña es demasiado corta")
    h = bcrypt.hashpw(clave.encode(), bcrypt.gensalt()).decode()
    pool.open()
    aplicar_schema()
    with pool.connection() as c:
        c.execute("insert into usuarios(usuario,nombre,rol,password_hash) values (%s,%s,%s,%s) "
                  "on conflict (usuario) do update set nombre=excluded.nombre, rol=excluded.rol, "
                  "password_hash=excluded.password_hash, activo=true", (usuario, nombre, rol, h))
    print("Usuario listo:", usuario, f"({rol})")


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "crear-usuario":
        crear_usuario(sys.argv[2], sys.argv[3], " ".join(sys.argv[4:]) or sys.argv[2])
    else:
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "3000")))
