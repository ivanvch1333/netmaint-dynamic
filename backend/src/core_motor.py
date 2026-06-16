"""
Módulo Core: Motor de Evaluación Energética y Ambiental para Nodos ISP.
Aplica principios SOLID (Responsabilidad Única e Inversión de Dependencias).
No tiene dependencias de Frameworks Web ni Bases de Datos.
"""

from typing import Dict, Any


class ValidadorEntrada:
    """
    Responsabilidad: Validar de forma estricta los datos métricos ingresados
    por el técnico en el nodo físico para evitar inconsistencias en la base de datos.
    """
    
    @staticmethod
    def validar_metricas_nodo(voltaje: float, autonomia: int, temperatura: float) -> None:
        """
        Valida que los parámetros físicos del nodo estén dentro de límites reales.
        Lanza ValueError si se detectan datos fuera de rango o negativos.
        """
        # Validación de voltaje comercial (Monitoreo de corriente alterna en sitio)
        if voltaje < 0:
            raise ValueError("Error de consistencia: El voltaje de entrada comercial no puede ser negativo.")
        if voltaje > 300:
            raise ValueError("Alerta de Seguridad: El voltaje de entrada supera el límite de diseño operativo (>300V).")
            
        # Validación de autonomía de las baterías UPS (Tiempo de respaldo estimado)
        if autonomia < 0:
            raise ValueError("Error de consistencia: La autonomía de la UPS no puede ser un tiempo negativo.")
            
        # Validación de temperatura de la cabina o sala del nodo (Higrotérmica)
        if temperatura < -40 or temperatura > 80:
            raise ValueError("Error de consistencia: La temperatura ambiental registrada está fuera de límites físicos terrestres.")


class MotorEvaluacionAmbiental:
    """
    Responsabilidad: Procesar métricas, evaluar estados de riesgo operativo,
    calcular la eficiencia energética (PUE) y estimar el impacto ambiental (CO2).
    """
    
    # Factor de emisión estándar de CO2 (e.g., 0.4 kg CO2 por kWh consumido)
    FACTOR_EMISION_CO2_KG_KWH = 0.40

    def __init__(self, validador: ValidadorEntrada):
        """
        Inyección de dependencias para asegurar desacoplamiento y facilitar pruebas unitarias.
        """
        self.validador = validador

    def calcular_eficiencia_pue(self, energia_total_nodo_kw: float, energia_equipos_red_kw: float) -> float:
        """
        Calcula el PUE (Power Usage Effectiveness).
        Fórmula: Energía Total Consumida por el Nodo / Energía Usada solo por Routers/Switches.
        El valor ideal es 1.0 (Máxima eficiencia ecológica).
        """
        if energia_equipos_red_kw <= 0:
            raise ValueError("Error de cálculo: La energía consumida por los equipos de red debe ser mayor a cero.")
        if energia_total_nodo_kw < energia_equipos_red_kw:
            raise ValueError("Error de consistencia: La energía total del nodo no puede ser menor a la consumida por el hardware de red.")
            
        pue = energia_total_nodo_kw / energia_equipos_red_kw
        return round(pue, 2)

    def evaluar_estado_critico(
        self, 
        voltaje: float, 
        autonomia: int, 
        temperatura: float,
        energia_total_nodo_kw: float = 1.2,
        energia_equipos_red_kw: float = 1.0
    ) -> Dict[str, Any]:
        """
        Analiza las variables recolectadas en el terreno y genera un diagnóstico 
        operativo y de impacto ambiental de forma síncrona.
        """
        # 1. Ejecutar validación de consistencia
        self.validador.validar_metricas_nodo(voltaje, autonomia, temperatura)
        
        # 2. Inicializar flags de diagnóstico
        alerta_climatizacion = "Normal"
        alerta_electrica = "Estable"
        requiere_atencion_inmediata = False
        
        # 3. Lógica del sistema de climatización y eficiencia térmica
        if temperatura > 25.0:
            alerta_climatizacion = "Sobrecalentamiento: Riesgo térmico en hardware de red o falla de ventilación."
            requiere_atencion_inmediata = True
        elif temperatura < 15.0:
            alerta_climatizacion = "Subenfriamiento: Desperdicio energético innecesario en aire acondicionado."
            
        # 4. Lógica del sistema eléctrico y autonomía del nodo
        if voltaje == 0:
            alerta_electrica = "Alerta Crítica: Corte de energía externa detectado. Operando 100% con baterías UPS."
            requiere_atencion_inmediata = True
            
        if autonomia < 15:
            # Si tiene poca autonomía, es crítico (aún más si no hay energía externa)
            alerta_electrica = "Crítico: Autonomía de baterías por debajo del umbral mínimo de seguridad (<15 mins)."
            requiere_atencion_inmediata = True
            
        # 5. Cálculos energéticos y huella ecológica
        pue_calculado = self.calcular_eficiencia_pue(energia_total_nodo_kw, energia_equipos_red_kw)
        
        # Consumo diario estimado en kWh
        consumo_diario_kwh = energia_total_nodo_kw * 24
        # Estimación de CO2 emitido al día (kg)
        huella_co2_dia = round(consumo_diario_kwh * self.FACTOR_EMISION_CO2_KG_KWH, 2)
        
        return {
            "pue_eficiencia": pue_calculado,
            "diagnostico_climatizacion": alerta_climatizacion,
            "diagnostico_electrico": alerta_electrica,
            "requiere_atencion_inmediata": requiere_atencion_inmediata,
            "huella_carbono_estimada_kg_dia": huella_co2_dia
        }