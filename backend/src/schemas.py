from pydantic import BaseModel, Field, ConfigDict, field_validator
from datetime import date, datetime
from typing import Optional, Any, List
import re

def _validar_email(v: str) -> str:
    """Validación básica de formato email sin dependencias externas."""
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', v):
        raise ValueError('Formato de correo electrónico inválido')
    return v.lower().strip()

# ==========================================
# ESQUEMAS DE AUTENTICACIÓN Y 2FA
# ==========================================

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)

class TokenResponse(BaseModel):
    token: str
    rol: str
    username: str
    nombre: str
    usa_2fa: bool = False

class Login2FARequerido(BaseModel):
    """Respuesta cuando el usuario tiene 2FA activo: el frontend debe pedir el código TOTP."""
    requiere_2fa: bool = True
    session_2fa_token: str
    mensaje: str = "Ingresa el código de 6 dígitos de tu aplicación autenticadora."

class Validar2FARequest(BaseModel):
    """Payload para el segundo paso del login con 2FA."""
    session_2fa_token: str = Field(..., min_length=10)
    codigo_totp: str = Field(..., min_length=6, max_length=6)

class Setup2FAResponse(BaseModel):
    """Respuesta del endpoint de configuración inicial del QR."""
    totp_secret: str
    otpauth_url: str
    qr_url: str  # URL de la imagen PNG del QR para mostrar en el frontend

class Verificar2FASetupRequest(BaseModel):
    """Payload para confirmar que el QR fue escaneado correctamente."""
    codigo_totp: str = Field(..., min_length=6, max_length=6)


# ==========================================
# ESQUEMAS DE CONFIGURACIÓN DE EMPRESA
# ==========================================

class ConfiguracionEmpresaCreate(BaseModel):
    nombre_empresa: str = Field(..., min_length=1, max_length=150)
    nit_ruc: str = Field(..., min_length=1, max_length=50)

class ConfiguracionEmpresaResponse(BaseModel):
    id: int
    nombre_empresa: str
    nit_ruc: str
    url_logo_local: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# ESQUEMAS DE PARÁMETROS DEL CHECKLIST
# ==========================================

class ParametroChecklistCreate(BaseModel):
    categoria: str = Field(..., description="Categoría del parámetro de checklist")
    pregunta_texto: str = Field(..., min_length=1, max_length=255)

class ParametroChecklistResponse(BaseModel):
    id: int
    categoria: str
    pregunta_texto: str
    activo: bool

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# ESQUEMAS DE USUARIO
# ==========================================

class UserCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    username: str = Field(..., min_length=3, max_length=50)
    correo: str = Field(..., min_length=5, max_length=100)
    password: str = Field(..., min_length=8)
    rol: str = Field(..., description="Debe ser 'SuperAdministrador', 'Administrador' o 'Tecnico'")

    @field_validator('password')
    @classmethod
    def validar_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres.")
        if not any(c.isupper() for c in v):
            raise ValueError("La contraseña debe contener al menos una letra mayúscula.")
        if not re.search(r'[^a-zA-Z0-9]', v):
            raise ValueError("La contraseña debe contener al menos un carácter especial (ej. @, #, $, *, etc.).")
        return v

    @field_validator('correo')
    @classmethod
    def validar_correo(cls, v: str) -> str:
        return _validar_email(v)

    @field_validator('rol')
    @classmethod
    def validar_rol(cls, v: str) -> str:
        if v not in ["SuperAdministrador", "Administrador", "Tecnico"]:
            raise ValueError("El rol debe ser 'SuperAdministrador', 'Administrador' o 'Tecnico'")
        return v

class UserResponse(BaseModel):
    id: int
    nombre: str
    username: str
    correo: str
    rol: str
    totp_activo: bool = False
    totp_verificado: bool = False

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# ESQUEMAS DE NODO
# ==========================================

class NodoCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    tipo: str = Field(..., description="Debe ser 'Core', 'Distribución' o 'Acceso'")
    criticidad: str = Field(..., description="Debe ser 'Alta', 'Media' o 'Baja'")
    latitud: float = Field(..., ge=-90.0, le=90.0)
    longitud: float = Field(..., ge=-180.0, le=180.0)

    @field_validator('tipo')
    @classmethod
    def validar_tipo(cls, v: str) -> str:
        if v not in ["Core", "Distribución", "Acceso"]:
            raise ValueError("Tipo no válido.")
        return v

    @field_validator('criticidad')
    @classmethod
    def validar_criticidad(cls, v: str) -> str:
        if v not in ["Alta", "Media", "Baja"]:
            raise ValueError("Criticidad no válida.")
        return v

class NodoResponse(BaseModel):
    id: int
    nombre: str
    tipo: str
    criticidad: str
    latitud: float
    longitud: float

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# ESQUEMAS DE ORDEN DE TRABAJO
# ==========================================

class OrdenCreate(BaseModel):
    nodo_id: int
    tecnico_id: Optional[int] = None

class OrdenResponse(BaseModel):
    id: int
    nodo_id: int
    tecnico_id: Optional[int]
    estado: str
    fecha_creacion: date
    fecha_inicio: Optional[datetime] = None
    fecha_cierre: Optional[datetime] = None
    nodo: Optional[NodoResponse] = None
    tecnico: Optional[UserResponse] = None

    model_config = ConfigDict(from_attributes=True)

class TecnicoDashboardResponse(BaseModel):
    ordenes: List[OrdenResponse]
    checklist_plantilla: List[ParametroChecklistResponse]


# ==========================================
# ESQUEMAS DE REPORTE
# ==========================================

class ReporteResponse(BaseModel):
    id: int
    orden_trabajo_id: int
    respuestas_json: Any
    observaciones_generales: Optional[str]
    novedades_detectadas: Optional[str]
    recomendaciones: Optional[str] = None
    fotos_urls: Any
    firma_tecnico_url: Optional[str] = None
    latitud_tecnico: Optional[float] = None
    longitud_tecnico: Optional[float] = None
    ingeniero_autorizador: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# ESQUEMAS DE AUDITORÍA
# ==========================================

class LogAuditoriaResponse(BaseModel):
    id: int
    usuario_id: str
    accion: str
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# ESQUEMA PANEL DE SEGURIDAD (Super Admin)
# ==========================================

class SeguridadUsuarioInfo(BaseModel):
    id: int
    nombre: str
    username: str
    rol: str
    totp_activo: bool
    totp_verificado: bool
    intentos_fallidos: int
    bloqueado_hasta: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
