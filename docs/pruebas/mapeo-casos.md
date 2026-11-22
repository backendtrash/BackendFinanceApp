# Mapeo de los casos de prueba (paquete 4.1)

**Fecha:** 22/11/2026 · Cada caso de la Evidencia 2 contra la prueba automática
que ya lo cubre. "Script" es `scripts/casos_prueba.py`, que corre el caso
contra producción con las cuentas de prueba (`casos-funcionales.md`).

| Caso | Módulo / RF | Prueba automática que lo cubre | ¿Requiere prueba manual? |
|---|---|---|---|
| CP-01 | Registro (RF01) | `test_privacy_consent.py`: sin aceptar el aviso, 422; con aceptarlo, se guarda la versión | **Sí**: el correo de confirmación llega y el enlace abre la sesión |
| CP-02 | Sesión (RF01, RNF-02) | `test_auth_required.py`: cada ruta protegida responde 401 sin token. Script | **Sí**: la pantalla redirige al acceso |
| CP-03 | Gastos en otra divisa (RF02, RF05) | Script (gasto de US$100). `test_currencies.py` cubre la actualización del tipo de cambio, no la conversión al guardar | No |
| CP-04 | Validación de gastos (RF02) | Script (monto negativo → 422 con el campo). **Sin prueba unitaria** | No |
| CP-05 | Confidencialidad (RNF-01) | `test_isolation.py` (36 casos, dos cuentas reales) y `test_not_found.py`. Script | No |
| CP-06 | Categorías (RF04) | `test_integrity.py`: `test_a_referenced_category_is_refused`, `test_the_delete_endpoint_answers_409`. Script | **Sí**: la pantalla muestra el motivo |
| CP-07 | Presupuestos y alertas (RF06) | Script (alerta al 82% en el historial). **Sin prueba unitaria** de la creación de la alerta | No |
| CP-08 | Recurrentes (RF07) | `test_integrity.py`: el cursor avanza antes de escribir; `test_pure_calcs.py`: avance mensual y semanal. Script | No |
| CP-09 | Recurrentes, idempotencia (RF07) | `test_integrity.py`: `test_processing_twice_in_one_day_creates_one_transaction`, `test_a_lost_claim_writes_nothing`. Script | No |
| CP-10 | Analítica sin datos (RF10) | `test_analytics_calcs.py`: `test_dashboard_empty_month_is_all_zeros_not_an_error`. Script (cuenta B) | **Sí**: las gráficas muestran su mensaje de vacío |
| CP-11 | Analítica con volumen (RF10, RNF-03) | Script: 200 movimientos, tiempo y totales. `test_analytics_rf10.py` cubre los totales de la comparación anual | No |
| CP-12 | Reporte PDF (RF12) | Ninguna: el PDF se genera en el navegador. Verificado a mano el 14/11 (`docs/verificacion-RF12.md`) | **Sí** |
| CP-13 | Renovación de sesión (RNF-02) | `test_auth_tokens.py`. Script: la API renueva el token | **Sí**: un formulario a medio llenar se envía sin perder datos |
| CP-14 | Compatibilidad móvil (RNF-06) | Ninguna | **Sí**: las once pantallas en un teléfono |

## Lo que la suite no cubre

- **Interfaz:** la redirección al acceso (CP-02), el mensaje al borrar una
  categoría en uso (CP-06), el mensaje de las gráficas vacías (CP-10) y el
  formulario con el token vencido (CP-13).
- **Correo:** la confirmación del registro (CP-01).
- **Vista en celular:** las once pantallas (CP-14).
- **Reporte PDF** (CP-12): se genera en el navegador.

Tres casos solo los cubre el script contra producción, sin prueba unitaria:
la conversión a pesos al guardar (CP-03), el rechazo del monto negativo
(CP-04) y la creación de la alerta de presupuesto (CP-07).
