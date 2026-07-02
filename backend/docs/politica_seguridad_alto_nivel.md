🌐 POLÍTICA DE SEGURIDAD DE LA INFORMACIÓN DE ALTO NIVEL (EGSI V3.0)

Organización: NetMaint-Dynamic PRO (Cátedra de Ingeniería de Software)

Estándar Base: Esquema Gubernamental de Seguridad de la Información (EGSI v3.0 / Ecuador)

Marco Legal: Ley Orgánica de Protección de Datos Personales (LOPDP)

Vigencia: Largo Plazo / Revisión Anual

1. Antecedentes

El incremento acelerado en la dependencia de la infraestructura crítica de telecomunicaciones exige que los proveedores de servicios de internet (ISPs) mantengan un control físico, ambiental y lógico impecable sobre sus nodos de distribución. La plataforma NetMaint-Dynamic PRO nace como la solución síncrona en tiempo real para digitalizar, automatizar y auditar el mantenimiento mensual de estos nodos.

Debido a que el sistema procesa datos operativos altamente sensibles (voltajes de red, niveles de autonomía de UPS, estados higrotérmicos de racks), información de control de accesos, logs de auditoría e información de carácter personal de los técnicos (nombres, coordenadas geográficas de visita y firmas digitalizadas del personal de campo), la ausencia de directrices de seguridad expone al ISP a riesgos catastróficos. Estos incluyen la interrupción masiva de la conectividad, fuga de propiedad intelectual, adulteración maliciosa de checklists e incumplimientos graves de la Ley Orgánica de Protección de Datos Personales (LOPDP) de Ecuador.

Para mitigar estos escenarios y definir un compromiso ineludible por parte de la dirección del proyecto, se establece la presente Política de Seguridad de la Información de Alto Nivel, la cual adopta las mejores prácticas de la norma internacional ISO/IEC 27001:2022 y los controles mandatorios del Esquema Gubernamental de Seguridad de la Información (EGSI v3.0).

2. Objetivo de la Política

Establecer las directrices de seguridad, principios fundamentales y reglas de control para asegurar la confidencialidad, integridad y disponibilidad (CID) de todos los activos de información lógicos, físicos y de red de la plataforma NetMaint-Dynamic PRO.

La política garantiza el blindaje técnico del motor de procesamiento, el almacenamiento seguro de la multimedia y el resguardo criptográfico de los datos de carácter personal frente a cualquier amenaza interna o externa, accidental o deliberada.

3. Política de Seguridad de la Información

3.1. Descripción de la Política (Principios Rectores)

La dirección de desarrollo y operaciones del proyecto adopta los siguientes compromisos y principios fundamentales en la arquitectura de NetMaint-Dynamic PRO:

A. Principio de Mínimo Privilegio (Control de Acceso)

Todo acceso a los datos e interfaces de la aplicación web estará restringido por defecto. Los usuarios técnicos únicamente poseerán permisos para interactuar con su agenda del día y llenar checklists, prohibiendo estrictamente su acceso a configuraciones de marca blanca, modificación de preguntas o eliminación de bitácoras de auditoría (RBAC).

B. Codificación Segura y Validación en el Core

Ningún dato recolectado en terreno por el técnico en su dispositivo móvil será persistido de forma automática en la base de datos sin pasar por los filtros de consistencia física programados de forma pura en core_motor.py. El sistema rechazará de forma síncrona voltajes, temperaturas o autonomías fuera de la física real mediante excepciones ValueError.

C. Integridad e Inmutabilidad en la Auditoría

La base de datos PostgreSQL mantendrá una tabla dedicada a registros históricos de eventos críticas (LogAuditoria). Por diseño de arquitectura, esta tabla tendrá deshabilitadas las sentencias de actualización (UPDATE) y eliminación (DELETE). Todo cambio de preguntas del checklist o alteración de datos deberá quedar registrado con marca de tiempo del servidor e IP de origen de manera permanente.

D. Protección y Privacidad por Diseño (LOPDP)

En cumplimiento de los Artículos 37 y 39 de la LOPDP, la plataforma tratará los vectores de las firmas digitalizadas y contraseñas de los usuarios mediante cifrado criptográfico irreversible (hashes asimétricos y salts robustos con algoritmo $bcrypt$). Queda estrictamente prohibido el almacenamiento de credenciales o trazos de firma en texto plano.

E. Minimización y Sanitización de Multimedia

Para prevenir denegaciones de servicio por saturación de almacenamiento y bloquear inyecciones de código malicioso oculto en metadatos, todas las evidencias fotográficas de los nodos sufrirán un proceso obligatorio de compresión y sanitización física a nivel del servidor (pesando $\le 500\text{ KB}$ mediante la librería Pillow) antes de su almacenamiento en la nube.

3.2. Declaración de los Objetivos de Seguridad de la Información

Para medir la eficacia de esta política, se establecen los siguientes objetivos cuantificables en la plataforma:

Garantía de Disponibilidad: Mantener un índice de disponibilidad del motor de validación y de la Web App móvil superior al $99.9\%$ mensual, permitiendo a los técnicos realizar inspecciones síncronas sin interrupciones.

Mitigación del Error Humano en Base de Datos: Reducir a un $0\%$ la tasa de registros inconsistentes o negativos en la base de datos central a través del filtro de excepciones de core_motor.py.

Cifrado de Comunicaciones en Tránsito: Lograr que el $100\%$ de los paquetes de datos y formularios transmitidos por redes celulares públicas 4G/5G transiten bajo protocolo seguro cifrado HTTPS/TLS.

Protección Legal frente a la LOPDP: Lograr cero incidentes de fuga de datos personales o firmas digitalizadas, aplicando esquemas criptográficos asimétricos sobre la información sensible del personal de campo.

3.3. Roles y Responsabilidades

Para asegurar que la política de seguridad se mantenga viva, se definen los siguientes roles estratégicos:

┌────────────────────────────────────────────────────────────────────────┐
│                        ESTRUCTURA DE GOBERNANZA                        │
├───────────────────────────────────┬────────────────────────────────────┤
│           ROL ASIGNADO            │      RESPONSABILIDAD PRINCIPAL     │
├───────────────────────────────────┼────────────────────────────────────┤
│ Comité de Seguridad (Dirección)   │ - Aprobación del presupuesto de TI │
│                                   │ - Revisión anual de políticas      │
├───────────────────────────────────┼────────────────────────────────────┤
│ Oficial de Seguridad (OSI)        │ - Auditar logs inmutables          │
│                                   │ - Gestión de accesos y tokens JWT  │
├───────────────────────────────────┼────────────────────────────────────┤
│ Administrador del Sistema (TI)    │ - Mantenimiento del Servidor/DB    │
│                                   │ - Configurar certificados SSL/TLS  │
├───────────────────────────────────┼────────────────────────────────────┤
│ Técnico de Terreno (Campo)        │ - Reporte oportuno de novedades    │
│                                   │ - Uso ético de credenciales        │
└───────────────────────────────────┴────────────────────────────────────┘


A. Comité de Seguridad de la Información (CSI)

Responsabilidad: Máximo órgano rector del sistema. Aprueba las directrices de seguridad, evalúa periódicamente la matriz de riesgos bajo la norma ISO 27005 y autoriza cambios sustanciales en la infraestructura.

B. Oficial de Seguridad de la Información (OSI)

Responsabilidad: Monitorea de manera activa el cumplimiento del EGSI v3.0. Coordina la ejecución de pruebas unitarias y de estrés, audita periódicamente la tabla de LogAuditoria, emite alertas de seguridad y gestiona los tokens criptográficos de sesión JWT.

C. Administrador de Sistemas y Base de Datos (DBA/SysAdmin)

Responsabilidad: Implementa físicamente los controles técnicos definidos. Responsable de garantizar el correcto funcionamiento de PostgreSQL, mantener los contenedores backend actualizados, aplicar parches de seguridad en el servidor Docker y asegurar la vigencia de los certificados SSL/TLS.

D. Personal Técnico y Operadores de Terreno (Usuarios Finales)

Responsabilidad: Utilizar los canales síncronos de la Web App móvil con responsabilidad y ética profesional. Tienen estrictamente prohibido compartir credenciales de acceso, falsificar coordenadas de georreferenciación o eludir los flujos de firmas manuscritas digitales.

3.4. Alcance y Usuarios

La presente política es de aplicación obligatoria e inmediata para:

Todo el código fuente de backend, frontend y bases de datos que conformen el ecosistema de NetMaint-Dynamic PRO.

Todos los empleados directos del ISP, desarrolladores de software, administradores de red y supervisores de operaciones.

El personal de campo y técnicos de telecomunicaciones (incluyendo personal contratado directamente o personal subcontratado mediante cuadrillas externas/tercerizadas).

Toda la infraestructura física de servidores y dispositivos móviles que interactúen mediante peticiones HTTPS con la plataforma.

3.5. Comunicación de la Política

Para garantizar el conocimiento colectivo de las reglas de seguridad, se establecen tres directrices de comunicación:

Publicación Digital: La versión vigente de esta política debe estar disponible de forma permanente en la sección de documentación de soporte de la Web App en la ruta visible para todos los administradores.

Capacitación Inducción: Todo técnico que ingrese a laborar en terreno para el ISP deberá completar de manera mandatoria una sesión de inducción de $30\text{ minutos}$ sobre el uso seguro del portal de OTs, la captura de firmas y el reporte ético de inconsistencias.

Notificación de Modificaciones: Cualquier actualización de la política o cambio en la gestión de contraseñas de la base de datos se comunicará automáticamente mediante notificaciones de consola en la aplicación web para los roles administrativos.

3.6. Excepciones y Sanciones

A. Gestión de Excepciones

Cualquier desviación temporal o excepción justificada a los controles descritos en esta política (por ejemplo, deshabilitar temporalmente las OTs masivas para mantenimiento de servidores) deberá ser documentada formalmente por el OSI y aprobada por escrito por el Comité de Seguridad de la Información, fijando una fecha límite de expiración para dicha excepción.

B. Sanciones por Incumplimiento

La violación voluntaria o negligente de las directrices de esta política dará lugar a:

Para Personal Interno o Técnicos Directos: Aplicación de medidas disciplinarias severas de conformidad con lo establecido en el Reglamento Interno de Trabajo del ISP y el Código de Trabajo de Ecuador, las cuales pueden ir desde amonestaciones verbales, suspensión de accesos, hasta la desvinculación laboral justificada.

Para Cuadrillas Subcontratadas (Terceros): Rescisión unilateral del contrato comercial de servicios de mantenimiento por vulnerar los estándares de seguridad de red del ISP, sin perjuicio de las acciones legales, civiles o penales aplicables bajo la legislación del país (especialmente por manipulación fraudulenta de información de auditoría o filtración de datos de la LOPDP).

4. Glosario de Términos

EGSI: Esquema Gubernamental de Seguridad de la Información de Ecuador. Estándar obligatorio de ciberseguridad para la administración pública y sus ecosistemas.

LOPDP: Ley Orgánica de Protección de Datos Personales de Ecuador, que rige la confidencialidad, privacidad y el uso legítimo de datos de personas naturales.

PUE (Power Usage Effectiveness): Métrica estándar internacional para evaluar la eficiencia energética en centros de datos y nodos de telecomunicaciones.

JWT (JSON Web Token): Estándar abierto basado en JSON para la creación de tokens de acceso asertivos y firmados criptográficamente para la autorización web.

Inmutabilidad: Atributo de la información que garantiza que los datos registrados no puedan ser modificados, alterados ni eliminados por ningún actor.

Sanitización: Proceso técnico que elimina metadatos ocultos y códigos incrustados dañinos de archivos multimedia e imágenes de evidencia antes de almacenarlos.

5. Documentos de Referencia

Ley Orgánica de Protección de Datos Personales (Ecuador - LOPDP).

Esquema Gubernamental de Seguridad de la Información de Ecuador (EGSI v3.0).

Norma Técnica Ecuatoriana NTE INEN-ISO/IEC 27001:2022 (Sistemas de Gestión de Seguridad de la Información).

Norma Técnica Ecuatoriana NTE INEN-ISO/IEC 27005:2022 (Directrices para la Gestión de Riesgos de Seguridad de la Información).

Reglamento Interno y Código de Trabajo de la República del Ecuador.

6. Firmas de Responsabilidad

Acción

Nombre y Cargo                                                               Firma / Validación

Elaborado por:

Klever Ivan / Oficial de Seguridad de la Información (OSI)                   VALIDADO DIGITALMENTE

Revisado por:

Ivan Valle / Presidente del Comité de Seguridad de TI                        VALIDADO DIGITALMENTE

Aprobado por:

Máxima Autoridad / Director de Desarrollo de NetMaint PRO                     VALIDADO DIGITALMENTE