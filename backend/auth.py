import os
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select

from backend.database import get_session
from backend.models import User
from dotenv import load_dotenv

# Cargar variables de entorno. Ruta explícita: bajo `uvicorn --reload` en Windows,
# load_dotenv() sin ruta no encuentra backend/.env en el subproceso spawneado.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# Configuración de seguridad desde .env
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY no está definida. Crea backend/.env a partir de backend/.env.example"
    )
ALGORITHM = "HS256"

# 7 días. Antes eran 30 minutos, que es exactamente lo que dura el pomodoro
# más largo: al terminar uno, el POST que lo guardaba recibía un 401, el
# frontend cerraba sesión y el usuario perdía la sesión de golpe.
# Subirlo invalida los tokens ya emitidos: todos vuelven a iniciar sesión una vez.
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica si la contraseña es correcta"""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def get_password_hash(password: str) -> str:
    """Hashea una contraseña"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Crea un token de acceso JWT"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    return encoded_jwt


def get_current_user(
    token: str = Depends(oauth2_scheme), 
    session: Session = Depends(get_session)
) -> User:
    """Obtiene el usuario actual desde el token JWT"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        
        if email is None:
            raise credentials_exception
            
    except JWTError:
        raise credentials_exception
    
    # Usar SQLModel/select en lugar de query
    user = session.exec(select(User).where(User.email == email)).first()
    
    if user is None:
        raise credentials_exception
    
    return user
