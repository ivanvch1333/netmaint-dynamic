import hashlib
import secrets
import pyotp
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session

from src.database import get_db
import src.models as models


def hash_password(password: str) -> str:
    """
    Hash seguro PBKDF2-HMAC-SHA256 con salt dinámico de 16 bytes y 100,000 iteraciones.
    Formato: pbkdf2_sha256$iteraciones$salt$hash
    """
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return "pbkdf2_sha256$100000${}${}".format(salt, key.hex())


def verify_password(password: str, hashed: str) -> bool:
    """Verifica que la contraseña plana coincide con el hash almacenado."""
    try:
        if not hashed or "$" not in hashed:
            return False
        parts = hashed.split('$')
        if len(parts) != 4:
            return False
        _, iterations, salt, key_hex = parts
        key_new = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            int(iterations)
        )
        return key_new.hex() == key_hex
    except Exception:
        return False


def generar_token() -> str:
    """Genera un token de sesión seguro de 64 caracteres hexadecimales (256 bits)."""
    return secrets.token_hex(32)


def generar_totp_secret() -> str:
    """Genera una clave secreta TOTP aleatoria base32 compatible con Google Authenticator."""
    return pyotp.random_base32()


def generar_otpauth_url(username: str, secret: str, empresa: str = "NetMaint-PRO") -> str:
    """
    Genera la URL otpauth:// estándar para crear el QR de configuración.
    Compatible con Google Authenticator, Authy y Microsoft Authenticator.
    """
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=username, issuer_name=empresa)


def verificar_codigo_totp(secret: str, codigo: str) -> bool:
    """
    Verifica un código TOTP de 6 dígitos.
    Acepta una ventana de ±1 intervalo (30 segundos) para tolerancia de desincronización de reloj.
    """
    try:
        totp = pyotp.TOTP(secret)
        return totp.verify(codigo, valid_window=1)
    except Exception:
        return False


def obtener_usuario_actual(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> models.Usuario:
    """
    Dependencia de FastAPI: valida el Bearer Token de sesión y retorna el usuario autenticado.
    Rechaza tokens inválidos, expirados o de sesiones 2FA temporales no completadas.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales de acceso no válidas o sesión expirada.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not authorization:
        raise credentials_exception

    token = authorization
    if authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]

    sesion = db.query(models.SesionUsuario).filter(
        models.SesionUsuario.token == token,
        models.SesionUsuario.fecha_expiracion > datetime.utcnow()
    ).first()

    if not sesion or not sesion.usuario:
        raise credentials_exception

    return sesion.usuario
