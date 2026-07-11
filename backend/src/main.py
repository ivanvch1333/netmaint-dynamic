import io
import os
import json
import logging
import qrcode
import base64
from typing import List, Optional, Union
from datetime import date, datetime, timedelta
import uvicorn

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, Response
from sqlalchemy.orm import Session
from PIL import Image
from contextlib import asynccontextmanager

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from src.database import engine, Base, get_db, SessionLocal
import src.models as models
import src.schemas as schemas
from src.scheduler import start_scheduler, stop_scheduler
from src.auth import (
    hash_password, verify_password, generar_token,
    generar_totp_secret, generar_otpauth_url, verificar_codigo_totp,
    obtener_usuario_actual
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MainAPI")

UPLOAD_DIR = "uploads"
STATIC_DIR = "static"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

# ------------------------------------------------------------------
# SEEDING DE DATOS INICIALES
# ------------------------------------------------------------------
def seed_initial_data(db: Session):
    """Inicializa la configuración corporativa y los usuarios por defecto."""

    # Configuración de empresa
    if not db.query(models.ConfiguracionEmpresa).first():
        db.add(models.ConfiguracionEmpresa(
            nombre_empresa="Nodos de Internet S.A.",
            nit_ruc="900.123.456-7",
            url_logo_local=None
        ))

    # Super Administrador con 2FA preparado
    if not db.query(models.Usuario).filter(models.Usuario.username == "admin_red").first():
        secret_2fa = generar_totp_secret()
        super_admin = models.Usuario(
            nombre="Super Administrador Red",
            username="admin_red",
            correo="admin_red@netmaint.com",
            password_hash=hash_password("Ectronix2620@"),
            rol="SuperAdministrador",
            totp_secret=secret_2fa,
            totp_activo=False,      # Se activa cuando el admin escanea el QR por primera vez
            totp_verificado=False
        )
        db.add(super_admin)
        logger.info("=" * 60)
        logger.info("SUPER ADMINISTRADOR CREADO")
        logger.info("  Usuario  : admin_red")
        logger.info("  Password : Ectronix2620@")
        logger.info("  2FA      : Configura escaneando el QR en:")
        logger.info("  http://localhost:8000/auth/2fa/setup")
        logger.info("  (inicia sesion primero como admin_red)")
        logger.info("=" * 60)

    # Técnico por defecto
    if not db.query(models.Usuario).filter(models.Usuario.username == "tecnico").first():
        db.add(models.Usuario(
            nombre="Técnico Operativo",
            username="tecnico",
            correo="tecnico@netmaint.com",
            password_hash=hash_password("Tecnico123*"),
            rol="Tecnico",
            totp_activo=False,
            totp_verificado=False
        ))

    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Creando/Verificando tablas en la base de datos...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        seed_initial_data(db)
    except Exception as e:
        db.rollback()
        logger.error("Error al inicializar datos: {}".format(str(e)))
    finally:
        db.close()

    logger.info("Iniciando programador de tareas...")
    start_scheduler()
    yield
    logger.info("Deteniendo programador de tareas...")
    stop_scheduler()


app = FastAPI(
    title="NetMaint-Dynamic PRO",
    description="Sistema de Gestión de Mantenimiento de Nodos con 2FA-TOTP.",
    version="4.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ==============================================================
# AUTENTICACIÓN — PASO 1: Login con usuario y contraseña
# ==============================================================

@app.post("/auth/login", tags=["Autenticación"])
def login(credentials: schemas.LoginRequest, db: Session = Depends(get_db)):
    """
    Paso 1 del login.
    - Si el usuario NO tiene 2FA activo: devuelve el token de acceso completo.
    - Si el usuario SÍ tiene 2FA activo y verificado: devuelve un token temporal
      y solicita al frontend que pida el código TOTP.
    """
    try:
        user = db.query(models.Usuario).filter(
            models.Usuario.username == credentials.username
        ).first()

        if user:
            # 1. Verificar si la cuenta está bloqueada temporalmente por seguridad
            if user.bloqueado_hasta and user.bloqueado_hasta > datetime.utcnow():
                segundos_restantes = int((user.bloqueado_hasta - datetime.utcnow()).total_seconds())
                minutos_restantes = max(1, segundos_restantes // 60)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cuenta bloqueada temporalmente por seguridad debido a 5 intentos fallidos. Intente nuevamente en {} minuto(s).".format(minutos_restantes)
                )

        if not user or not verify_password(credentials.password, user.password_hash):
            # Registrar intento fallido
            if user:
                user.intentos_fallidos += 1
                if user.intentos_fallidos >= 5:
                    user.bloqueado_hasta = datetime.utcnow() + timedelta(minutes=15)
                    db.add(models.LogAuditoria(
                        usuario_id=credentials.username,
                        accion="Cuenta bloqueada por seguridad (5 intentos fallidos consecutivos).",
                        timestamp=datetime.utcnow()
                    ))
                else:
                    db.add(models.LogAuditoria(
                        usuario_id=credentials.username,
                        accion="Intento de login fallido (intento {}/5).".format(user.intentos_fallidos),
                        timestamp=datetime.utcnow()
                    ))
                db.commit()
            else:
                db.add(models.LogAuditoria(
                    usuario_id=credentials.username,
                    accion="Intento de login fallido (usuario inexistente: {}).".format(credentials.username),
                    timestamp=datetime.utcnow()
                ))
                db.commit()

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Nombre de usuario o contraseña incorrectos."
            )

        # Login correcto -> Reiniciar contadores
        user.intentos_fallidos = 0
        user.bloqueado_hasta = None
        db.commit()

        # Limpiar sesiones expiradas
        db.query(models.SesionUsuario).filter(
            models.SesionUsuario.usuario_id == user.id,
            models.SesionUsuario.fecha_expiracion < datetime.utcnow()
        ).delete()
        db.query(models.Token2FA).filter(
            models.Token2FA.usuario_id == user.id,
            models.Token2FA.fecha_expiracion < datetime.utcnow()
        ).delete()

        # Si tiene 2FA activo y verificado → exigir segundo factor
        if user.totp_activo and user.totp_verificado:
            token_temp = generar_token()
            db.add(models.Token2FA(
                token_temporal=token_temp,
                usuario_id=user.id,
                fecha_expiracion=datetime.utcnow() + timedelta(minutes=5)
            ))
            db.commit()
            return {
                "requiere_2fa": True,
                "session_2fa_token": token_temp,
                "mensaje": "Ingresa el código de 6 dígitos de tu aplicación autenticadora."
            }

        # Sin 2FA → generar sesión completa directamente
        token = generar_token()
        db.add(models.SesionUsuario(
            token=token,
            usuario_id=user.id,
            fecha_expiracion=datetime.utcnow() + timedelta(hours=24)
        ))
        db.commit()

        return {
            "token": token,
            "rol": user.rol,
            "username": user.username,
            "nombre": user.nombre,
            "usa_2fa": False
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("Error en login: {}".format(str(e)))
        raise HTTPException(status_code=500, detail="Error al procesar el inicio de sesión.")


# ==============================================================
# AUTENTICACIÓN — PASO 2: Validar código TOTP
# ==============================================================

@app.post("/auth/2fa/validar", tags=["Autenticación 2FA"])
def validar_2fa(payload: schemas.Validar2FARequest, db: Session = Depends(get_db)):
    """
    Paso 2 del login con 2FA. Valida el código TOTP de 6 dígitos.
    Si es correcto, emite el token de acceso completo.
    """
    # Buscar el token temporal
    registro_temp = db.query(models.Token2FA).filter(
        models.Token2FA.token_temporal == payload.session_2fa_token,
        models.Token2FA.fecha_expiracion > datetime.utcnow()
    ).first()

    if not registro_temp:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión 2FA expirada o inválida. Por favor inicia sesión de nuevo."
        )

    user = registro_temp.usuario
    if not user or not user.totp_secret:
        raise HTTPException(status_code=400, detail="El usuario no tiene 2FA configurado.")

    # Verificar el código TOTP
    if not verificar_codigo_totp(user.totp_secret, payload.codigo_totp):
        db.add(models.LogAuditoria(
            usuario_id=str(user.id),
            accion="Intento de validación 2FA fallido para usuario: {}.".format(user.username),
            timestamp=datetime.utcnow()
        ))
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Código TOTP incorrecto o expirado. Revisa tu aplicación autenticadora."
        )

    # Código correcto → Eliminar token temporal y crear sesión real
    db.delete(registro_temp)

    token = generar_token()
    db.add(models.SesionUsuario(
        token=token,
        usuario_id=user.id,
        fecha_expiracion=datetime.utcnow() + timedelta(hours=24)
    ))
    db.add(models.LogAuditoria(
        usuario_id=str(user.id),
        accion="Login exitoso con doble autenticación (2FA-TOTP) para: {}.".format(user.username),
        timestamp=datetime.utcnow()
    ))
    db.commit()

    return {
        "token": token,
        "rol": user.rol,
        "username": user.username,
        "nombre": user.nombre,
        "usa_2fa": True
    }


# ==============================================================
# AUTENTICACIÓN — SETUP 2FA: Generar QR de configuración
# ==============================================================

@app.get("/auth/2fa/setup", tags=["Autenticación 2FA"])
def obtener_qr_2fa(
    current_user: models.Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db)
):
    """
    Genera y retorna la imagen PNG del código QR para escanear con Google Authenticator.
    Crea o reutiliza el totp_secret del usuario. Debe llamarse antes de verificar-setup.
    """
    try:
        # Si no tiene secret aún, generarlo
        if not current_user.totp_secret:
            current_user.totp_secret = generar_totp_secret()
            db.commit()

        empresa = db.query(models.ConfiguracionEmpresa).first()
        nombre_empresa = empresa.nombre_empresa if empresa else "NetMaint-PRO"

        otpauth_url = generar_otpauth_url(
            username=current_user.username,
            secret=current_user.totp_secret,
            empresa=nombre_empresa
        )

        # Generar imagen QR en memoria con Pillow como backend
        qr = qrcode.QRCode(version=1, box_size=8, border=4)
        qr.add_data(otpauth_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        return Response(content=buf.read(), media_type="image/png")

    except Exception as e:
        logger.error("Error generando QR 2FA: {}".format(str(e)))
        raise HTTPException(status_code=500, detail="Error al generar el código QR.")


@app.post("/auth/2fa/verificar-setup", tags=["Autenticación 2FA"])
def verificar_setup_2fa(
    payload: schemas.Verificar2FASetupRequest,
    current_user: models.Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db)
):
    """
    Verifica el primer código TOTP del usuario tras escanear el QR.
    Si es correcto, activa el 2FA definitivamente en su cuenta.
    """
    if not current_user.totp_secret:
        raise HTTPException(status_code=400, detail="Primero debes obtener el QR desde /auth/2fa/setup.")

    if not verificar_codigo_totp(current_user.totp_secret, payload.codigo_totp):
        raise HTTPException(
            status_code=400,
            detail="Código incorrecto. Asegúrate de haber escaneado el QR y que la hora de tu dispositivo sea correcta."
        )

    current_user.totp_activo = True
    current_user.totp_verificado = True
    db.add(models.LogAuditoria(
        usuario_id=str(current_user.id),
        accion="Doble autenticación (2FA-TOTP) activada correctamente para: {}.".format(current_user.username),
        timestamp=datetime.utcnow()
    ))
    db.commit()

    return {"detail": "2FA activado correctamente. A partir de ahora necesitarás tu código autenticador para ingresar."}


@app.delete("/auth/2fa/desactivar/{usuario_id}", tags=["Autenticación 2FA"])
def desactivar_2fa_usuario(
    usuario_id: int,
    current_user: models.Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db)
):
    """
    Permite al Super Administrador desactivar el 2FA de cualquier usuario
    (por ejemplo, si un técnico pierde su teléfono).
    """
    if current_user.rol != "SuperAdministrador":
        raise HTTPException(status_code=403, detail="Solo el Super Administrador puede desactivar 2FA de otros usuarios.")

    target_user = db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    target_user.totp_activo = False
    target_user.totp_verificado = False
    target_user.totp_secret = generar_totp_secret()  # Regenerar secret por seguridad

    db.add(models.LogAuditoria(
        usuario_id=str(current_user.id),
        accion="Super Admin {} desactivó 2FA del usuario: {}.".format(current_user.username, target_user.username),
        timestamp=datetime.utcnow()
    ))
    db.commit()
    return {"detail": "2FA desactivado. El usuario puede volver a configurarlo desde /auth/2fa/setup."}


@app.post("/auth/logout", tags=["Autenticación"])
def logout(
    current_user: models.Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db)
):
    try:
        db.query(models.SesionUsuario).filter(
            models.SesionUsuario.usuario_id == current_user.id
        ).delete()
        db.commit()
        return {"detail": "Sesión cerrada correctamente."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Error al cerrar la sesión.")


# ==============================================================
# PANEL DE SEGURIDAD — Super Administrador
# ==============================================================

@app.get("/seguridad/usuarios", response_model=List[schemas.SeguridadUsuarioInfo], tags=["Panel de Seguridad"])
def panel_seguridad_usuarios(
    current_user: models.Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db)
):
    """Retorna el estado de seguridad 2FA de todos los usuarios (Solo Super Admin)."""
    if current_user.rol != "SuperAdministrador":
        raise HTTPException(status_code=403, detail="Acceso exclusivo del Super Administrador.")
    return db.query(models.Usuario).all()


@app.get("/seguridad/sesiones-activas", tags=["Panel de Seguridad"])
def sesiones_activas(
    current_user: models.Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db)
):
    """Retorna el número de sesiones activas en el sistema (Solo Super Admin)."""
    if current_user.rol != "SuperAdministrador":
        raise HTTPException(status_code=403, detail="Acceso exclusivo del Super Administrador.")
    total = db.query(models.SesionUsuario).filter(
        models.SesionUsuario.fecha_expiracion > datetime.utcnow()
    ).count()
    return {"sesiones_activas": total}


@app.get("/seguridad/intentos-fallidos", tags=["Panel de Seguridad"])
def intentos_fallidos(
    current_user: models.Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db)
):
    """Retorna los últimos intentos de login fallidos registrados en auditoría (Solo Super Admin)."""
    if current_user.rol != "SuperAdministrador":
        raise HTTPException(status_code=403, detail="Acceso exclusivo del Super Administrador.")
    logs = db.query(models.LogAuditoria).filter(
        models.LogAuditoria.accion.like("%fallido%")
    ).order_by(models.LogAuditoria.timestamp.desc()).limit(20).all()
    return [{"id": l.id, "usuario": l.usuario_id, "accion": l.accion, "timestamp": str(l.timestamp)} for l in logs]


# ==============================================================
# CONFIGURACIÓN DE EMPRESA
# ==============================================================

@app.get("/configuracion", response_model=schemas.ConfiguracionEmpresaResponse, tags=["Configuración Empresa"])
def obtener_configuracion(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(obtener_usuario_actual)
):
    config = db.query(models.ConfiguracionEmpresa).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuración no encontrada.")
    return config


@app.put("/configuracion", response_model=schemas.ConfiguracionEmpresaResponse, tags=["Configuración Empresa"])
def actualizar_configuracion(
    config_data: schemas.ConfiguracionEmpresaCreate,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(obtener_usuario_actual)
):
    if current_user.rol not in ["Administrador", "SuperAdministrador"]:
        raise HTTPException(status_code=403, detail="Acceso denegado.")
    config = db.query(models.ConfiguracionEmpresa).first()
    if not config:
        config = models.ConfiguracionEmpresa()
        db.add(config)
    config.nombre_empresa = config_data.nombre_empresa
    config.nit_ruc = config_data.nit_ruc
    db.commit()
    db.refresh(config)
    return config


@app.post("/configuracion/logo", response_model=schemas.ConfiguracionEmpresaResponse, tags=["Configuración Empresa"])
def subir_logo(
    logo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(obtener_usuario_actual)
):
    if current_user.rol not in ["Administrador", "SuperAdministrador"]:
        raise HTTPException(status_code=403, detail="Acceso denegado.")
    if logo.content_type not in ["image/jpeg", "image/png", "image/jpg"]:
        raise HTTPException(status_code=400, detail="Formato no permitido. Debe ser JPG o PNG.")
    ext = os.path.splitext(logo.filename)[1] or ".png"
    filename = "logo_empresa{}".format(ext)
    filepath = os.path.join(UPLOAD_DIR, filename)
    file_bytes = logo.file.read()
    with open(filepath, "wb") as f:
        f.write(file_bytes)
    config = db.query(models.ConfiguracionEmpresa).first()
    if not config:
        config = models.ConfiguracionEmpresa(nombre_empresa="Empresa", nit_ruc="000")
        db.add(config)
    config.url_logo_local = "/uploads/{}".format(filename)
    db.commit()
    db.refresh(config)
    return config


# ==============================================================
# CHECKLIST DINÁMICO
# ==============================================================

@app.post("/admin/checklist", response_model=schemas.ParametroChecklistResponse, status_code=201, tags=["Checklist"])
def crear_parametro(
    parametro: schemas.ParametroChecklistCreate,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(obtener_usuario_actual)
):
    if current_user.rol not in ["Administrador", "SuperAdministrador"]:
        raise HTTPException(status_code=403, detail="Acceso denegado.")
    nuevo = models.ParametroChecklist(
        categoria=parametro.categoria, pregunta_texto=parametro.pregunta_texto, activo=True
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


@app.get("/admin/checklist", response_model=List[schemas.ParametroChecklistResponse], tags=["Checklist"])
def listar_parametros(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(obtener_usuario_actual)
):
    return db.query(models.ParametroChecklist).filter(models.ParametroChecklist.activo == True).all()


@app.delete("/admin/checklist/{param_id}", tags=["Checklist"])
def eliminar_parametro_checklist(
    param_id: int,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(obtener_usuario_actual)
):
    """Elimina (desactiva) un parámetro del checklist. Solo administradores."""
    if current_user.rol not in ["Administrador", "SuperAdministrador"]:
        raise HTTPException(status_code=403, detail="Acceso denegado.")
    param = db.query(models.ParametroChecklist).filter(models.ParametroChecklist.id == param_id).first()
    if not param:
        raise HTTPException(status_code=404, detail="Parámetro no encontrado.")
    param.activo = False
    db.add(models.LogAuditoria(
        usuario_id=str(current_user.id),
        accion="Eliminación del parámetro de checklist ID {} ({})".format(param_id, param.pregunta_texto),
        timestamp=datetime.utcnow()
    ))
    db.commit()
    return {"detail": "Parámetro eliminado correctamente."}


# ==============================================================
# USUARIOS
# ==============================================================

@app.post("/usuarios", response_model=schemas.UserResponse, status_code=201, tags=["Usuarios"])
def crear_usuario(
    usuario: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(obtener_usuario_actual)
):
    if current_user.rol not in ["Administrador", "SuperAdministrador"]:
        raise HTTPException(status_code=403, detail="Permiso denegado.")
    existe = db.query(models.Usuario).filter(
        (models.Usuario.correo == usuario.correo) | (models.Usuario.username == usuario.username)
    ).first()
    if existe:
        raise HTTPException(status_code=400, detail="El correo o usuario ya está registrado.")
    nuevo = models.Usuario(
        nombre=usuario.nombre, username=usuario.username, correo=usuario.correo,
        password_hash=hash_password(usuario.password), rol=usuario.rol,
        totp_activo=False, totp_verificado=False
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


@app.get("/usuarios", response_model=List[schemas.UserResponse], tags=["Usuarios"])
def listar_usuarios(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(obtener_usuario_actual)
):
    return db.query(models.Usuario).all()


@app.delete("/usuarios/{usuario_id}", tags=["Usuarios"])
def eliminar_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(obtener_usuario_actual)
):
    if current_user.rol not in ["Administrador", "SuperAdministrador"]:
        raise HTTPException(status_code=403, detail="Permiso denegado.")
        
    if current_user.id == usuario_id:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propio usuario.")
        
    usuario = db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        
    if usuario.username == "admin_red":
        raise HTTPException(status_code=400, detail="No se puede eliminar el Super Administrador principal.")

    db.add(models.LogAuditoria(
        usuario_id=str(current_user.id),
        accion="Eliminó al usuario/técnico {} (Rol: {}).".format(usuario.username, usuario.rol),
        timestamp=datetime.utcnow()
    ))
    
    db.delete(usuario)
    db.commit()
    return {"detail": "Usuario/técnico eliminado correctamente."}


# ==============================================================
# NODOS
# ==============================================================

@app.post("/nodos", response_model=schemas.NodoResponse, status_code=201, tags=["Nodos"])
def crear_nodo(
    nodo: schemas.NodoCreate,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(obtener_usuario_actual)
):
    if current_user.rol not in ["Administrador", "SuperAdministrador"]:
        raise HTTPException(status_code=403, detail="Permiso denegado.")
    nuevo = models.Nodo(
        nombre=nodo.nombre, tipo=nodo.tipo, criticidad=nodo.criticidad,
        latitud=nodo.latitud, longitud=nodo.longitud
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


@app.get("/nodos", response_model=List[schemas.NodoResponse], tags=["Nodos"])
def listar_nodos(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(obtener_usuario_actual)
):
    return db.query(models.Nodo).all()


# ==============================================================
# ÓRDENES DE TRABAJO
# ==============================================================

@app.post("/ordenes", response_model=schemas.OrdenResponse, status_code=201, tags=["Órdenes"])
def crear_orden_manual(
    orden: schemas.OrdenCreate,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(obtener_usuario_actual)
):
    if current_user.rol not in ["Administrador", "SuperAdministrador"]:
        raise HTTPException(status_code=403, detail="Permiso denegado.")
    nodo = db.query(models.Nodo).filter(models.Nodo.id == orden.nodo_id).first()
    if not nodo:
        raise HTTPException(status_code=404, detail="Nodo no encontrado.")
    if orden.tecnico_id:
        tecnico = db.query(models.Usuario).filter(
            models.Usuario.id == orden.tecnico_id, models.Usuario.rol == "Tecnico"
        ).first()
        if not tecnico:
            raise HTTPException(status_code=404, detail="Técnico no encontrado.")
    nueva = models.OrdenTrabajo(
        nodo_id=orden.nodo_id, tecnico_id=orden.tecnico_id,
        estado="Pendiente", fecha_creacion=date.today()
    )
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


@app.get("/ordenes", response_model=List[schemas.OrdenResponse], tags=["Órdenes"])
def listar_todas_ordenes(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(obtener_usuario_actual)
):
    return db.query(models.OrdenTrabajo).all()


@app.delete("/ordenes/{ot_id}", tags=["Órdenes"])
def eliminar_orden(
    ot_id: int,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(obtener_usuario_actual)
):
    if current_user.rol not in ["Administrador", "SuperAdministrador"]:
        raise HTTPException(status_code=403, detail="Permiso denegado.")
    ot = db.query(models.OrdenTrabajo).filter(models.OrdenTrabajo.id == ot_id).first()
    if not ot:
        raise HTTPException(status_code=404, detail="Orden no encontrada.")
    
    # Registrar la eliminación en la auditoría
    db.add(models.LogAuditoria(
        usuario_id=str(current_user.id),
        accion="Eliminó la orden de trabajo ID {} para el nodo ID {}.".format(ot.id, ot.nodo_id),
        timestamp=datetime.utcnow()
    ))
    
    db.delete(ot)
    db.commit()
    return {"detail": "Orden de trabajo eliminada correctamente."}


@app.post("/ordenes/{ot_id}/iniciar", response_model=schemas.OrdenResponse, tags=["Órdenes"])
def iniciar_orden(
    ot_id: int,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(obtener_usuario_actual)
):
    ot = db.query(models.OrdenTrabajo).filter(models.OrdenTrabajo.id == ot_id).first()
    if not ot:
        raise HTTPException(status_code=404, detail="Orden no encontrada.")
    if current_user.rol == "Tecnico" and ot.tecnico_id != current_user.id:
        raise HTTPException(status_code=403, detail="No puedes iniciar una orden que no tienes asignada.")
    if ot.estado != "Pendiente":
        raise HTTPException(status_code=400, detail="La orden debe estar en estado 'Pendiente'.")
    ot.estado = "En Progreso"
    db.commit()
    db.refresh(ot)
    return ot


@app.get("/ordenes/tecnico/me", response_model=schemas.TecnicoDashboardResponse, tags=["Módulo Técnico"])
def dashboard_tecnico_autenticado(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(obtener_usuario_actual)
):
    if current_user.rol != "Tecnico":
        raise HTTPException(status_code=403, detail="Acceso exclusivo para técnicos.")
    ordenes = db.query(models.OrdenTrabajo).filter(
        models.OrdenTrabajo.tecnico_id == current_user.id,
        models.OrdenTrabajo.estado.in_(["Pendiente", "En Progreso"])
    ).all()
    checklist = db.query(models.ParametroChecklist).filter(models.ParametroChecklist.activo == True).all()
    return {"ordenes": ordenes, "checklist_plantilla": checklist}


@app.get("/ordenes/tecnico/{tecnico_id}", response_model=schemas.TecnicoDashboardResponse, tags=["Módulo Técnico"])
def dashboard_tecnico_por_id(
    tecnico_id: int,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(obtener_usuario_actual)
):
    tecnico = db.query(models.Usuario).filter(
        models.Usuario.id == tecnico_id, models.Usuario.rol == "Tecnico"
    ).first()
    if not tecnico:
        raise HTTPException(status_code=404, detail="Técnico no encontrado.")
    ordenes = db.query(models.OrdenTrabajo).filter(
        models.OrdenTrabajo.tecnico_id == tecnico_id,
        models.OrdenTrabajo.estado.in_(["Pendiente", "En Progreso"])
    ).all()
    checklist = db.query(models.ParametroChecklist).filter(models.ParametroChecklist.activo == True).all()
    return {"ordenes": ordenes, "checklist_plantilla": checklist}


def procesar_y_guardar_imagen(file: UploadFile, ot_id: int, index: int) -> str:
    file_bytes = file.file.read()
    file_size_kb = len(file_bytes) / 1024
    ext = os.path.splitext(file.filename)[1] or ".jpg"
    filename = "ot_{}_foto_{}_{}{}".format(ot_id, index, int(datetime.utcnow().timestamp()), ext)
    filepath = os.path.join(UPLOAD_DIR, filename)
    if file_size_kb > 500:
        try:
            img = Image.open(io.BytesIO(file_bytes))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=75, optimize=True)
            compressed = buf.getvalue()
            if len(compressed) / 1024 > 500:
                w, h = img.size
                img = img.resize((w // 2, h // 2), Image.Resampling.LANCZOS)
                buf2 = io.BytesIO()
                img.save(buf2, format="JPEG", quality=60, optimize=True)
                compressed = buf2.getvalue()
            with open(filepath, "wb") as f:
                f.write(compressed)
        except Exception:
            with open(filepath, "wb") as f:
                f.write(file_bytes)
    else:
        with open(filepath, "wb") as f:
            f.write(file_bytes)
    return "/uploads/{}".format(filename)


def guardar_firma_base64(base64_str: str, ot_id: int) -> str:
    """
    Decodifica una cadena Base64 (formato data:image/png;base64,...)
    y la guarda en el directorio UPLOAD_DIR como archivo físico PNG.
    """
    try:
        if "," in base64_str:
            base64_str = base64_str.split(",")[1]
        
        file_bytes = base64.b64decode(base64_str)
        filename = "firma_ot_{}_{}.png".format(ot_id, int(datetime.utcnow().timestamp()))
        filepath = os.path.join(UPLOAD_DIR, filename)
        
        with open(filepath, "wb") as f:
            f.write(file_bytes)
            
        return "/uploads/{}".format(filename)
    except Exception as e:
        logger.error("Error al guardar firma base64: {}".format(str(e)))
        raise HTTPException(status_code=400, detail="Firma digital corrupta o formato no compatible.")


@app.post("/ordenes/{ot_id}/completar", response_model=schemas.OrdenResponse, tags=["Módulo Técnico"])
def completar_orden(
    ot_id: int,
    respuestas_json: str = Form(...),
    observaciones_generales: Optional[str] = Form(None),
    novedades_detectadas: Optional[str] = Form(None),
    recomendaciones: Optional[str] = Form(None),
    firma_base64: str = Form(...),
    descripciones_fotos: Optional[str] = Form(None),
    fotos: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(obtener_usuario_actual)
):
    ot = db.query(models.OrdenTrabajo).filter(models.OrdenTrabajo.id == ot_id).first()
    if not ot:
        raise HTTPException(status_code=404, detail="Orden no encontrada.")
    if ot.estado != "En Progreso":
        raise HTTPException(status_code=400, detail="La orden debe estar 'En Progreso'.")
    try:
        respuestas_dict = json.loads(respuestas_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Formato respuestas_json inválido.")

    try:
        descripciones_list = json.loads(descripciones_fotos) if descripciones_fotos else []
    except Exception:
        descripciones_list = []

    # Guardar firma digital
    firma_url = guardar_firma_base64(firma_base64, ot_id)

    guardadas_urls = []
    for i, foto in enumerate(fotos):
        if foto.content_type not in ["image/jpeg", "image/png", "image/jpg"]:
            continue
        url = procesar_y_guardar_imagen(foto, ot_id, i + 1)
        desc = descripciones_list[i] if i < len(descripciones_list) else ""
        guardadas_urls.append({"url": url, "descripcion": desc})

    if not guardadas_urls:
        raise HTTPException(status_code=400, detail="Debes subir al menos una foto en formato JPG o PNG.")

    db.add(models.ReporteMantenimiento(
        orden_trabajo_id=ot_id, respuestas_json=respuestas_dict,
        observaciones_generales=observaciones_generales,
        novedades_detectadas=novedades_detectadas,
        recomendaciones=recomendaciones,
        fotos_urls=guardadas_urls,
        firma_tecnico_url=firma_url
    ))
    ot.estado = "Completada"
    ot.fecha_cierre = date.today()
    db.add(models.LogAuditoria(
        usuario_id=str(current_user.id),
        accion="Técnico {} finalizó mantenimiento, firmó reporte y subió {} fotos en Nodo ID {}.".format(
            current_user.username, len(guardadas_urls), ot.nodo_id
        ),
        timestamp=datetime.utcnow()
    ))
    db.commit()
    db.refresh(ot)
    return ot


# ==============================================================
# REPORTE PDF (ReportLab)
# ==============================================================

@app.get("/ordenes/{ot_id}/reporte/pdf", tags=["Reportes"])
def descargar_reporte_pdf(ot_id: int, db: Session = Depends(get_db)):
    try:
        ot = db.query(models.OrdenTrabajo).filter(models.OrdenTrabajo.id == ot_id).first()
        if not ot:
            raise HTTPException(status_code=404, detail="Orden no encontrada.")
        if not ot.reporte:
            raise HTTPException(status_code=400, detail="La orden no posee un reporte registrado.")

        empresa = db.query(models.ConfiguracionEmpresa).first()
        nombre_empresa = empresa.nombre_empresa if empresa else "Nodos de Internet S.A."
        nit_ruc = empresa.nit_ruc if empresa else ""
        logo_url = empresa.url_logo_local if empresa else None

        db_preguntas = db.query(models.ParametroChecklist).all()
        dicc_preguntas = {p.id: (p.pregunta_texto, p.categoria) for p in db_preguntas}

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
        styles = getSampleStyleSheet()

        s_title = ParagraphStyle("T", fontName="Helvetica-Bold", fontSize=18, textColor=colors.HexColor("#1A365D"), alignment=TA_LEFT)
        s_company = ParagraphStyle("C", fontName="Helvetica-Bold", fontSize=12, textColor=colors.HexColor("#2D3748"))
        s_nit = ParagraphStyle("N", fontName="Helvetica", fontSize=9, textColor=colors.HexColor("#718096"))
        s_heading = ParagraphStyle("H", fontName="Helvetica-Bold", fontSize=12, textColor=colors.HexColor("#2B6CB0"), spaceBefore=12, spaceAfter=6)
        s_body = ParagraphStyle("B", fontName="Helvetica", fontSize=9, textColor=colors.HexColor("#2D3748"))
        s_bold = ParagraphStyle("BB", fontName="Helvetica-Bold", fontSize=9, textColor=colors.HexColor("#2D3748"))
        s_danger = ParagraphStyle("D", fontName="Helvetica-Bold", fontSize=10, textColor=colors.HexColor("#C53030"))

        story = []

        # HEADER
        logo_path = None
        if logo_url:
            lp = os.path.join(os.getcwd(), logo_url.lstrip("/"))
            if os.path.exists(lp):
                logo_path = lp

        if logo_path:
            try:
                logo_fl = RLImage(logo_path, width=80, height=35)
                hdr_data = [[logo_fl, [Paragraph(nombre_empresa, s_company), Paragraph("NIT/RUC: {}".format(nit_ruc), s_nit)]]]
            except Exception:
                hdr_data = [[[Paragraph(nombre_empresa, s_company), Paragraph("NIT/RUC: {}".format(nit_ruc), s_nit)], ""]]
        else:
            hdr_data = [[[Paragraph(nombre_empresa, s_company), Paragraph("NIT/RUC: {}".format(nit_ruc), s_nit)], ""]]

        hdr_tbl = Table(hdr_data, colWidths=[200, 332])
        hdr_tbl.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
        story.append(hdr_tbl)
        story.append(Spacer(1, 15))
        div = Table([[""]], colWidths=[532])
        div.setStyle(TableStyle([('LINEBELOW', (0,0), (-1,-1), 1.5, colors.HexColor("#1A365D")), ('BOTTOMPADDING', (0,0), (-1,-1), 0), ('TOPPADDING', (0,0), (-1,-1), 0)]))
        story.append(div)
        story.append(Spacer(1, 10))
        story.append(Paragraph("REPORTE DE AUDITORÍA Y MANTENIMIENTO DE NODO", s_title))
        story.append(Spacer(1, 15))

        # INFO GENERAL
        info = [
            [Paragraph("OT ID:", s_bold), Paragraph(str(ot.id), s_body), Paragraph("Fecha Creación:", s_bold), Paragraph(str(ot.fecha_creacion), s_body)],
            [Paragraph("Estado:", s_bold), Paragraph(ot.estado, s_body), Paragraph("Fecha Cierre:", s_bold), Paragraph(str(ot.fecha_cierre or "N/A"), s_body)],
            [Paragraph("Técnico:", s_bold), Paragraph(ot.tecnico.nombre if ot.tecnico else "N/A", s_body), Paragraph("Correo:", s_bold), Paragraph(ot.tecnico.correo if ot.tecnico else "N/A", s_body)],
            [Paragraph("Nodo:", s_bold), Paragraph(ot.nodo.nombre, s_body), Paragraph("Tipo / Criticidad:", s_bold), Paragraph("{} / {}".format(ot.nodo.tipo, ot.nodo.criticidad), s_body)],
        ]
        info_tbl = Table(info, colWidths=[120, 146, 120, 146])
        info_tbl.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F7FAFC")), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")), ('TOPPADDING', (0,0), (-1,-1), 5), ('BOTTOMPADDING', (0,0), (-1,-1), 5)]))
        story.append(info_tbl)
        story.append(Spacer(1, 15))

        # CHECKLIST - Tabla con columnas Pass / Fail / Comentarios
        story.append(Paragraph("RESULTADOS DEL CHECKLIST DE MANTENIMIENTO", s_heading))
        s_pass = ParagraphStyle("PASS", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white, alignment=TA_CENTER)
        s_fail = ParagraphStyle("FAIL", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white, alignment=TA_CENTER)
        s_na   = ParagraphStyle("NA",   fontName="Helvetica",      fontSize=9, textColor=colors.HexColor("#555"), alignment=TA_CENTER)
        rows = [[Paragraph("Parámetro de Control", s_bold), Paragraph("PASS", s_bold), Paragraph("FAIL", s_bold), Paragraph("Comentarios", s_bold)]]
        style_cmds = [
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1A4A7A")),
            ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
            ('GRID',       (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
        ]
        respuestas = ot.reporte.respuestas_json
        if isinstance(respuestas, str):
            try: respuestas = json.loads(respuestas)
            except: respuestas = []
        if isinstance(respuestas, list):
            for idx, res in enumerate(respuestas):
                p_id   = res.get("parametro_id")
                valor  = str(res.get("valor", "N/A")).upper()
                comentario = res.get("comentario", "") or ""
                texto, cat = dicc_preguntas.get(p_id, ("ID {} no encontrado".format(p_id), "General"))
                row_num = idx + 1
                bg = colors.white if row_num % 2 == 0 else colors.HexColor("#F0F4F8")
                pass_cell = Paragraph("OK", s_pass) if valor in ["PASS", "CUMPLE", "OK"] else Paragraph("", s_na)
                fail_cell = Paragraph("FAIL", s_fail) if valor in ["FAIL", "FALLA", "NO CONFORME", "NO APLICA", "N/A"] else Paragraph("", s_na)
                rows.append([
                    Paragraph("{}: {}".format(cat, texto), s_body),
                    pass_cell,
                    fail_cell,
                    Paragraph(comentario, s_body)
                ])
                style_cmds.append(('BACKGROUND', (0, row_num), (-1, row_num), bg))
                if valor in ["PASS", "CUMPLE", "OK"]:
                    style_cmds.append(('BACKGROUND', (1, row_num), (1, row_num), colors.HexColor("#38A169")))
                if valor in ["FAIL", "FALLA", "NO CONFORME"]:
                    style_cmds.append(('BACKGROUND', (2, row_num), (2, row_num), colors.HexColor("#E53E3E")))
                if valor in ["N/A", "NO APLICA"]:
                    style_cmds.append(('BACKGROUND', (2, row_num), (2, row_num), colors.HexColor("#A0AEC0")))
        ck_tbl = Table(rows, colWidths=[240, 50, 50, 192])
        ck_tbl.setStyle(TableStyle(style_cmds))
        story.append(ck_tbl)
        story.append(Spacer(1, 15))

        # OBSERVACIONES GENERALES
        obs_txt = ot.reporte.observaciones_generales or "Sin observaciones registradas."
        obs_elements = [Paragraph("OBSERVACIONES GENERALES", s_heading)]
        obs_tbl = Table([[Paragraph(obs_txt, s_body)]], colWidths=[532])
        obs_tbl.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F7FAFC")), ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")), ('TOPPADDING', (0,0), (-1,-1), 8), ('BOTTOMPADDING', (0,0), (-1,-1), 8), ('LEFTPADDING', (0,0), (-1,-1), 10)]))
        obs_elements.append(obs_tbl)
        story.append(KeepTogether(obs_elements))
        story.append(Spacer(1, 10))

        # NOVEDADES Y ANOMALÍAS
        nov_txt = ot.reporte.novedades_detectadas or "Sin novedades registradas."
        nov_elements = [Paragraph("NOVEDADES Y ANOMALÍAS DETECTADAS", s_heading)]
        is_danger = ot.reporte.novedades_detectadas and ot.reporte.novedades_detectadas.strip()
        nov_tbl = Table([[Paragraph(nov_txt, s_body)]], colWidths=[532])
        nov_tbl.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#FFF5F5") if is_danger else colors.HexColor("#F7FAFC")), ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#FEB2B2") if is_danger else colors.HexColor("#E2E8F0")), ('TOPPADDING', (0,0), (-1,-1), 8), ('BOTTOMPADDING', (0,0), (-1,-1), 8), ('LEFTPADDING', (0,0), (-1,-1), 10)]))
        nov_elements.append(nov_tbl)
        story.append(KeepTogether(nov_elements))
        story.append(Spacer(1, 10))

        # RECOMENDACIONES
        rec_txt = ot.reporte.recomendaciones or "Sin recomendaciones adicionales."
        rec_elements = [Paragraph("RECOMENDACIONES", s_heading)]
        rec_tbl = Table([[Paragraph(rec_txt, s_body)]], colWidths=[532])
        rec_tbl.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#FFFBEB")), ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#F6E05E")), ('TOPPADDING', (0,0), (-1,-1), 8), ('BOTTOMPADDING', (0,0), (-1,-1), 8), ('LEFTPADDING', (0,0), (-1,-1), 10)]))
        rec_elements.append(rec_tbl)
        story.append(KeepTogether(rec_elements))
        story.append(Spacer(1, 15))

        # FOTOS GRID
        urls_fotos = ot.reporte.fotos_urls
        if isinstance(urls_fotos, str):
            try: urls_fotos = json.loads(urls_fotos)
            except: urls_fotos = []

        img_flowables = []
        if isinstance(urls_fotos, list):
            for item in urls_fotos:
                url = ""
                descripcion = ""
                if isinstance(item, dict):
                    url = item.get("url", "")
                    descripcion = item.get("descripcion", "")
                elif isinstance(item, str):
                    url = item
                    descripcion = ""

                if not url:
                    continue

                foto_path = os.path.join(os.getcwd(), url.lstrip("/"))
                if os.path.exists(foto_path):
                    try:
                        # Imagen flowable
                        img = RLImage(foto_path, width=230, height=160)
                        
                        # Sub-tabla para enmarcar foto y su descripción
                        cell_data = [[img]]
                        if descripcion:
                            cell_data.append([Spacer(1, 4)])
                            cell_data.append([Paragraph(descripcion, s_body)])
                        
                        # El marco (tarjeta) con borde y fondo
                        marco_tbl = Table(cell_data, colWidths=[240])
                        marco_tbl.setStyle(TableStyle([
                            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
                            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F7FAFC")),
                            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                            ('TOPPADDING', (0,0), (-1,-1), 8),
                            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
                            ('LEFTPADDING', (0,0), (-1,-1), 5),
                            ('RIGHTPADDING', (0,0), (-1,-1), 5),
                        ]))
                        img_flowables.append(marco_tbl)
                    except Exception as e:
                        logger.error("Error foto PDF: {}".format(str(e)))

        if img_flowables:
            fotos_els = [Paragraph("REGISTRO FOTOGRÁFICO EN SITIO", s_heading)]
            grid = []
            for i in range(0, len(img_flowables), 2):
                row = img_flowables[i:i+2]
                if len(row) == 1:
                    row.append("")
                grid.append(row)
            ft = Table(grid, colWidths=[260, 260])
            ft.setStyle(TableStyle([
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 15)
            ]))
            fotos_els.append(ft)
            story.append(KeepTogether(fotos_els))

        # FIRMA DIGITAL DEL TÉCNICO
        firma_path = None
        if ot.reporte.firma_tecnico_url:
            fp = os.path.join(os.getcwd(), ot.reporte.firma_tecnico_url.lstrip("/"))
            if os.path.exists(fp):
                firma_path = fp

        signature_elements = []
        signature_elements.append(Spacer(1, 15))
        signature_elements.append(Paragraph("FIRMA Y ACEPTACIÓN DEL MANTENIMIENTO", s_heading))
        signature_elements.append(Spacer(1, 5))
        
        if firma_path:
            try:
                firma_img = RLImage(firma_path, width=150, height=50)
                sig_data = [
                    [firma_img],
                    [Paragraph("_______________________________________", s_bold)],
                    [Paragraph("Técnico: {}".format(ot.tecnico.nombre if ot.tecnico else "N/A"), s_bold)],
                    [Paragraph("Usuario: {}".format(ot.tecnico.username if ot.tecnico else ""), s_body)]
                ]
            except Exception as e:
                logger.error("Error al cargar firma en PDF: {}".format(str(e)))
                sig_data = [
                    [Paragraph("_______________________________________", s_bold)],
                    [Paragraph("Técnico: {}".format(ot.tecnico.nombre if ot.tecnico else "N/A"), s_bold)],
                    [Paragraph("[Firmado electrónicamente]", s_body)]
                ]
        else:
            sig_data = [
                [Paragraph("_______________________________________", s_bold)],
                [Paragraph("Técnico: {}".format(ot.tecnico.nombre if ot.tecnico else "N/A"), s_bold)],
                [Paragraph("[Pendiente de Firma]", s_body)]
            ]
        
        sig_tbl = Table(sig_data, colWidths=[300])
        sig_tbl.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
            ('TOPPADDING', (0,0), (-1,-1), 2)
        ]))
        signature_elements.append(sig_tbl)
        story.append(KeepTogether(signature_elements))

        doc.build(story)
        buffer.seek(0)
        return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=reporte_ot_{}.pdf".format(ot_id)})

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error PDF: {}".format(str(e)))
        raise HTTPException(status_code=500, detail="Error al construir el PDF.")


# ==============================================================
# LOGS DE AUDITORÍA
# ==============================================================

@app.get("/logs", response_model=List[schemas.LogAuditoriaResponse], tags=["Auditoría"])
def listar_logs(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(obtener_usuario_actual)
):
    if current_user.rol not in ["Administrador", "SuperAdministrador"]:
        raise HTTPException(status_code=403, detail="Acceso denegado.")
    return db.query(models.LogAuditoria).order_by(models.LogAuditoria.timestamp.desc()).all()


# ==============================================================
# RAÍZ — Servir SPA
# ==============================================================

@app.get("/", response_class=HTMLResponse, tags=["UI"])
def read_root():
    filepath = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    return "<h3>NetMaint-Dynamic PRO — Falta index.html en static/</h3>"


if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
