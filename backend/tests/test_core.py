"""
Conjunto de Pruebas Unitarias para validar el Motor Core de NetMaint-Dynamic PRO.
Utiliza pytest para realizar aserciones de consistencia, excepciones y lógica de negocio.
"""

import pytest
from src.core_motor import ValidadorEntrada, MotorEvaluacionAmbiental


# ==========================================
# FIXTURES (Configuración del Entorno de Pruebas)
# ==========================================
@pytest.fixture
def motor_core() -> MotorEvaluacionAmbiental:
    """Retorna una instancia del motor configurada con su validador inyectado."""
    validador = ValidadorEntrada()
    return MotorEvaluacionAmbiental(validador)


# ==========================================
# PRUEBAS DEL CÁLCULO DE EFICIENCIA (PUE)
# ==========================================
def test_calculo_pue_correcto(motor_core):
    """Verifica que el cálculo del PUE devuelva la proporción correcta."""
    # 2.0 kW total / 1.0 kW hardware = 2.0 PUE
    assert motor_core.calcular_eficiencia_pue(2.0, 1.0) == 2.0
    # 1.2 kW total / 1.0 kW hardware = 1.2 PUE
    assert motor_core.calcular_eficiencia_pue(1.2, 1.0) == 1.2


def test_error_pue_equipos_red_cero(motor_core):
    """Verifica que falle si el consumo de red es cero o negativo (división inválida)."""
    with pytest.raises(ValueError, match="La energía consumida por los equipos de red debe ser mayor a cero."):
        motor_core.calcular_eficiencia_pue(1.5, 0)


def test_error_pue_incoherente_total_menor_que_red(motor_core):
    """Valida que la energía total del nodo nunca sea inferior a la de sus equipos individuales."""
    with pytest.raises(ValueError, match="La energía total del nodo no puede ser menor a la consumida por el hardware de red."):
        motor_core.calcular_eficiencia_pue(0.8, 1.2)


# ==========================================
# PRUEBAS DE VALIDACIÓN DE ENTRADAS FÍSICAS
# ==========================================
def test_error_voltaje_negativo(motor_core):
    """Valida que el sistema rechace lecturas eléctricas negativas."""
    with pytest.raises(ValueError, match="El voltaje de entrada comercial no puede ser negativo."):
        motor_core.evaluar_estado_critico(voltaje=-10, autonomia=30, temperatura=20.0)


def test_error_voltaje_sobrelimite(motor_core):
    """Valida que el sistema evite el registro de picos de voltaje imposibles."""
    with pytest.raises(ValueError, match="El voltaje de entrada supera el límite de diseño operativo"):
        motor_core.evaluar_estado_critico(voltaje=350, autonomia=30, temperatura=20.0)


def test_error_autonomia_negativa(motor_core):
    """Valida que no se permitan tiempos de respaldo negativos."""
    with pytest.raises(ValueError, match="La autonomía de la UPS no puede ser un tiempo negativo."):
        motor_core.evaluar_estado_critico(voltaje=120, autonomia=-5, temperatura=20.0)


def test_error_temperatura_extrema(motor_core):
    """Valida el bloqueo de lecturas higrotérmicas corruptas."""
    with pytest.raises(ValueError, match="La temperatura ambiental registrada está fuera de límites físicos"):
        motor_core.evaluar_estado_critico(voltaje=120, autonomia=30, temperatura=95.0)


# ==========================================
# PRUEBAS DE EVALUACIÓN DE ALERTAS DE NEGOCIO
# ==========================================
def test_estado_perfectamente_estable(motor_core):
    """Verifica el diagnóstico correcto bajo condiciones normales de operación."""
    resultado = motor_core.evaluar_estado_critico(voltaje=110, autonomia=45, temperatura=22.0)
    assert resultado["requiere_atencion_inmediata"] is False
    assert resultado["diagnostico_climatizacion"] == "Normal"
    assert resultado["diagnostico_electrico"] == "Estable"


def test_alerta_por_sobrecalentamiento(motor_core):
    """Valida la activación de banderas críticas al sobrepasar los 25°C."""
    resultado = motor_core.evaluar_estado_critico(voltaje=110, autonomia=30, temperatura=28.5)
    assert resultado["requiere_atencion_inmediata"] is True
    assert "Sobrecalentamiento" in resultado["diagnostico_climatizacion"]


def test_alerta_por_subenfriamiento(motor_core):
    """Valida la detección de desperdicio de aire acondicionado por debajo de 15°C."""
    resultado = motor_core.evaluar_estado_critico(voltaje=110, autonomia=30, temperatura=12.0)
    # Es alerta de eficiencia, pero no detiene la operación crítica obligatoriamente
    assert "Subenfriamiento" in resultado["diagnostico_climatizacion"]


def test_alerta_operacion_baterias_por_corte(motor_core):
    """Valida la detección de corte de energía comercial (0V)."""
    resultado = motor_core.evaluar_estado_critico(voltaje=0, autonomia=45, temperatura=20.0)
    assert resultado["requiere_atencion_inmediata"] is True
    assert "Corte de energía externa" in resultado["diagnostico_electrico"]


def test_alerta_autonomia_baterias_critica(motor_core):
    """Valida la alerta si las baterías cuentan con menos de 15 minutos."""
    resultado = motor_core.evaluar_estado_critico(voltaje=110, autonomia=10, temperatura=20.0)
    assert resultado["requiere_atencion_inmediata"] is True
    assert "Autonomía de baterías por debajo del umbral" in resultado["diagnostico_electrico"]