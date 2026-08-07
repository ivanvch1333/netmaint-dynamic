from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, Text, JSON, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from src.database import Base


class ConfiguracionEmpresa(Base):
    __tablename__ = "configuracion_empresa"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre_empresa = Column(String(150), nullable=False)
    url_logo_local = Column(String(255), nullable=True)
    url_footer_local = Column(String(255), nullable=True)
    nit_ruc = Column(String(50), nullable=False)


class ParametroChecklist(Base):
    __tablename__ = "parametros_checklist"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    categoria = Column(String(50), nullable=False)
    pregunta_texto = Column(String(255), nullable=False)
    activo = Column(Boolean, nullable=False, default=True)


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre = Column(String(100), nullable=False)
    username = Column(String(50), unique=True, index=True, nullable=False)
    correo = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    rol = Column(String(50), nullable=False)  # 'SuperAdministrador', 'Administrador', 'Tecnico'

    # Campos de doble autenticación (2FA-TOTP)
    totp_secret = Column(String(64), nullable=True)       # Clave secreta TOTP única por usuario
    totp_activo = Column(Boolean, nullable=False, default=False)      # Si tiene 2FA habilitado
    totp_verificado = Column(Boolean, nullable=False, default=False)  # Si ya completó el setup del QR

    # Campos de bloqueo de cuenta (Lockout Policy)
    intentos_fallidos = Column(Integer, nullable=False, default=0)
    bloqueado_hasta = Column(DateTime, nullable=True)

    # Relaciones
    ordenes_asignadas = relationship("OrdenTrabajo", back_populates="tecnico")
    sesiones = relationship("SesionUsuario", back_populates="usuario", cascade="all, delete-orphan")
    tokens_2fa = relationship("Token2FA", back_populates="usuario", cascade="all, delete-orphan")


class SesionUsuario(Base):
    __tablename__ = "sesiones_usuario"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    token = Column(String(100), unique=True, index=True, nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    fecha_expiracion = Column(DateTime, nullable=False)

    # Relaciones
    usuario = relationship("Usuario", back_populates="sesiones")


class Token2FA(Base):
    """
    Almacena tokens temporales de sesión pendiente de verificación 2FA.
    Expiran en 5 minutos. Al validar el código TOTP, se elimina y se crea una SesionUsuario real.
    """
    __tablename__ = "tokens_2fa"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    token_temporal = Column(String(100), unique=True, index=True, nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    fecha_expiracion = Column(DateTime, nullable=False)

    # Relaciones
    usuario = relationship("Usuario", back_populates="tokens_2fa")


class Nodo(Base):
    __tablename__ = "nodos"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre = Column(String(100), nullable=False)
    tipo = Column(String(50), nullable=False)
    criticidad = Column(String(20), nullable=False)
    latitud = Column(Float, nullable=False)
    longitud = Column(Float, nullable=False)

    ordenes_trabajo = relationship("OrdenTrabajo", back_populates="nodo")


class OrdenTrabajo(Base):
    __tablename__ = "ordenes_trabajo"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nodo_id = Column(Integer, ForeignKey("nodos.id", ondelete="CASCADE"), nullable=False)
    tecnico_id = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    estado = Column(String(20), nullable=False, default="Pendiente")
    fecha_creacion = Column(Date, nullable=False, default=datetime.utcnow)
    fecha_inicio = Column(DateTime, nullable=True)
    fecha_cierre = Column(DateTime, nullable=True)

    nodo = relationship("Nodo", back_populates="ordenes_trabajo")
    tecnico = relationship("Usuario", back_populates="ordenes_asignadas")
    reporte = relationship("ReporteMantenimiento", uselist=False, back_populates="orden_trabajo", cascade="all, delete-orphan")


class ReporteMantenimiento(Base):
    __tablename__ = "reportes_mantenimiento"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    orden_trabajo_id = Column(Integer, ForeignKey("ordenes_trabajo.id", ondelete="CASCADE"), nullable=False)
    respuestas_json = Column(JSON, nullable=False)
    observaciones_generales = Column(Text, nullable=True)
    novedades_detectadas = Column(Text, nullable=True)
    fotos_urls = Column(JSON, nullable=False, default=list)
    firma_tecnico_url = Column(String(255), nullable=True)
    recomendaciones = Column(Text, nullable=True)
    latitud_tecnico = Column(Float, nullable=True)
    longitud_tecnico = Column(Float, nullable=True)
    ingeniero_autorizador = Column(String(150), nullable=True)

    orden_trabajo = relationship("OrdenTrabajo", back_populates="reporte")


class LogAuditoria(Base):
    __tablename__ = "logs_auditoria"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    usuario_id = Column(String(100), nullable=False)
    accion = Column(String(255), nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
