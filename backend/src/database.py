import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Obtener URL de la base de datos desde el entorno, o usar un valor local por defecto.
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://postgres:macaraxd@localhost:5432/mantenimiento_nodos"
)

# Configurar el motor de base de datos
engine = create_engine(
    DATABASE_URL,
    echo=False
)

# Configurar fábrica de sesiones
SessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine
)

# Definir la clase Base declarativa para los modelos ORM
Base = declarative_base()

# Dependencia para obtener la sesión de base de datos en los endpoints de FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
