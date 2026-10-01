import os
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from backend.database import get_session
from backend.models import User
from backend.schemas import UserCreate, UserUpdate, UserResponse, Token, POMODORO_FIELDS
from backend.auth import (
    verify_password, 
    get_password_hash, 
    create_access_token,
    get_current_user,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from backend import ratelimit

router = APIRouter(tags=["auth"])


def clean_optional(value):
    """Un campo opcional en blanco se guarda como NULL, no como cadena vacía"""
    if value is None:
        return None
    return value.strip() or None


def registration_open() -> bool:
    """ALLOW_REGISTRATION=false en backend/.env cierra el registro de cuentas
    nuevas; las que ya existen siguen entrando. Se lee en cada request, así que
    basta con reiniciar el servicio tras cambiarlo. Sin la variable, abierto."""
    return os.getenv("ALLOW_REGISTRATION", "true").strip().lower() not in ("false", "0", "no")


@router.post("/register", response_model=UserResponse)
def register(user: UserCreate, request: Request, session: Session = Depends(get_session)):
    """
    Registra un nuevo usuario
    """
    if not registration_open():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El registro de cuentas nuevas está cerrado."
        )

    ip = ratelimit.client_ip(request)
    ratelimit.ensure_allowed(ratelimit.registrations, ip, "Se crearon demasiadas cuentas desde esta conexión.")

    # Verificar si el email ya existe
    db_user = session.exec(select(User).where(User.email == user.email)).first()
    
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El email ya está registrado"
        )
    
    # Crear nuevo usuario
    hashed_password = get_password_hash(user.password)
    new_user = User(
        email=user.email,
        hashed_password=hashed_password,
        display_name=clean_optional(user.display_name),
        first_name=clean_optional(user.first_name),
        last_name=clean_optional(user.last_name)
    )
    
    session.add(new_user)
    session.commit()
    session.refresh(new_user)
    # Solo cuentan las cuentas creadas: un email repetido no gasta intentos
    ratelimit.registrations.hit(ip)
    
    return new_user


@router.post("/login", response_model=Token)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(), 
    session: Session = Depends(get_session)
):
    """
    Inicia sesión y retorna token JWT
    """
    # Antes de tocar la base y bcrypt: una IP bloqueada no gasta ni CPU
    ip = ratelimit.client_ip(request)
    ratelimit.ensure_allowed(ratelimit.failed_logins, ip, "Demasiados intentos fallidos.")

    # Buscar usuario por email
    user = session.exec(select(User).where(User.email == form_data.username)).first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        ratelimit.failed_logins.hit(ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuario inactivo"
        )
    
    # Crear token de acceso
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, 
        expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
def read_current_user(current_user: User = Depends(get_current_user)):
    """
    Retorna el usuario dueño del token. El frontend lo usa al recargar la
    página, donde solo conserva el token y no sabe a quién pertenece.
    """
    return current_user


@router.patch("/me", response_model=UserResponse)
def update_current_user(
    user_in: UserUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Actualiza el perfil del usuario del token: alias, nombre y apellido.
    Es la vía para que una cuenta ya creada rellene unos campos que no
    existían cuando se registró. Email y contraseña no se tocan aquí.
    """
    # Aplicar solo los campos enviados (PATCH parcial)
    update_data = user_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "rest_days" or field in POMODORO_FIELDS:
            setattr(current_user, field, value)
        else:
            setattr(current_user, field, clean_optional(value))

    session.add(current_user)
    session.commit()
    session.refresh(current_user)

    return current_user
