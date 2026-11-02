# Registro de horas

Indicador P1. Horas reales por día o por sesión, por paquete de la EDT.

Se registra lo que se trabajó de verdad, el día que se trabajó. Las celdas
de horas vacías están pendientes de que el equipo las llene; no se estiman
a posteriori.

## Totales

| Periodo | Horas | Acumulado |
|---|---|---|
| Al corte del 11/10/2026 (semanas 1–5) | 75 | 75 |
| Semana 6 (12 al 18/10/2026) | 15 | 90 |
| Semana 7 (19 al 25/10/2026) | 15 | 105 |
| Semana 8 (26/10 al 01/11/2026) | 15 | 120 |

El acumulado de 90 h al 18/10 es el que usa el IAC de ese corte
(`kpis.md`: 92.8 ÷ 90 = 1.03).

## Por sesión

| Fecha | Paquete EDT | Horas | Qué se hizo |
|---|---|---|---|
| 11/10/2026 | 3.1 / 3.2 | | Adaptación al diseño de H2 (PR #1): alcance, migraciones, pruebas, integridad, documentación |
| 18/10/2026 | 3.2 | | Defecto 6: la API aplica las políticas por fila (PR #2) |
| 18/10/2026 | 3.1 | | Defecto 11: fecha de actualización del tipo de cambio (PR #2) |
| 18/10/2026 | 3.3 | | Frontend publicado y navegable: repo, rutas, sesión, errores (front PR #1) |
| 18/10/2026 | 3.2 | | Registros de KPIs, acta de analítica e integración continua (PR #3) |
| 18/10/2026 | 3.2 | | Base Supabase desde migraciones, API en Railway, prueba de aislamiento con dos cuentas (defectos 18–21) |
| 18/10/2026 | 3.2 | | CI: el workflow nunca ejecutaba pruebas (defecto 22); aislamiento obligatorio en CI |
| 18/10/2026 | 3.1 | | Defectos 15 (eliminar cuenta) y 16 (refresco de tasas solo admins) |
| 19/10/2026 | 3.3 | | Frontend en Vercel conectado a la API; CORS; prueba con dos cuentas en producción; defecto 23 |
| 19/10/2026 | 3.1 / 3.3 | | RF01: consentimiento del aviso de privacidad en el registro y aviso integral publicado (defecto 24) |
| 25/10/2026 | 3.5 | | AP-8: respaldo semanal cifrado y comprobado (defectos 25 y 26) |
| 25/10/2026 | 3.5 | | E7: verificación del esquema de producción contra las migraciones (defecto 27) |
| 25/10/2026 | 3.2 | | Defectos 7 y 8: migración 013, patrimonio con saldo inicial, tendencias desde el primer mes |
| 25/10/2026 | 3.1 / 3.4 | | Defecto 28: exportación de datos en la API; se retira "Reiniciar espacio" |
| 01/11/2026 | 3.6 | | Actas firmadas de analítica y de H3 al repositorio; defectos 7 y 8 cerrados |
| 01/11/2026 | 3.2 | | Defectos 9 y 10: una regla de proyección para todas las vistas (`app/projection.py`) |
| 01/11/2026 | 3.4 | | Proyección futura aparte en Análisis y en el plan del mes; defecto 29 |
| 01/11/2026 | 3.2 | | Verificación en producción de los defectos 7 a 10; registros del corte |
