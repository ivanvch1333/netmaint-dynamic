import logging
from datetime import date
from apscheduler.schedulers.background import BackgroundScheduler
from src.database import SessionLocal
from src.models import Nodo, OrdenTrabajo, Usuario

# Configurar logging para el scheduler
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BackgroundScheduler")

def ejecutar_cron_mensual():
    """
    Función autoejecutable en segundo plano.
    Consulta todos los nodos y genera una Orden de Trabajo mensual 'Pendiente'
    para cada uno de ellos, autoasignando técnicos de forma equitativa (si existen).
    """
    logger.info("Iniciando generación de órdenes de trabajo mensuales...")
    db = SessionLocal()
    try:
        # Obtener todos los nodos registrados
        nodos = db.query(Nodo).all()
        if not nodos:
            logger.warning("No se encontraron nodos registrados. No se crearon órdenes.")
            return

        # Obtener los técnicos disponibles para asignar de forma equitativa
        tecnicos = db.query(Usuario).filter(Usuario.rol == "Tecnico").all()
        num_tecnicos = len(tecnicos)
        
        ordenes_creadas = 0
        for index, nodo in enumerate(nodos):
            # Asignación de técnico (si existen registrados, de lo contrario None)
            tecnico_id = tecnicos[index % num_tecnicos].id if num_tecnicos > 0 else None
            
            nueva_orden = OrdenTrabajo(
                nodo_id=nodo.id,
                tecnico_id=tecnico_id,
                estado="Pendiente",
                fecha_creacion=date.today(),
                fecha_cierre=None
            )
            db.add(nueva_orden)
            ordenes_creadas += 1

        db.commit()
        logger.info(f"Generación mensual completada. Se crearon {ordenes_creadas} órdenes de trabajo.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error al ejecutar el cron mensual: {str(e)}")
    finally:
        db.close()

# Inicialización del Scheduler de Fondo
scheduler = BackgroundScheduler()

def start_scheduler():
    """
    Inicia el programador de tareas y añade el job.
    """
    # Se ejecuta de forma real el día 1 de cada mes a las 00:00 (medianoche)
    scheduler.add_job(
        ejecutar_cron_mensual,
        trigger="cron",
        day=1,
        hour=0,
        minute=0,
        id="cron_mensual_nodos",
        replace_existing=True
    )
    
    if not scheduler.running:
        scheduler.start()
        logger.info("BackgroundScheduler iniciado en modo mensual real (día 1 de cada mes).")

def stop_scheduler():
    """
    Detiene el programador de tareas limpiando los recursos.
    """
    if scheduler.running:
        scheduler.shutdown()
        logger.info("BackgroundScheduler apagado correctamente.")
