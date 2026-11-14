# Flujos de extremo a extremo (paquete 3.5)

**Fecha:** 13/11/2026 · **Cuenta:** `prueba-a` · **Contra:** producción

H4 pide que los flujos principales funcionen de extremo a extremo. Los que
pasan por la API los recorre `scripts/e2e_api.py`, igual que lo hace el
frontend, comprobando el resultado en cada paso. Lo que crea queda marcado
`[e2e]` y se borra al terminar cada flujo, pase o falle. Un flujo que todavía
no se puede comprobar se reporta como pendiente, nunca como aprobado.

## Por la API

|---|---|---|
| Gastos: alta, edición y borrado | ✅ Pasa | alta, lectura, edición del monto, borrado y 404 después |
| Ingresos: alta, edición y borrado | ✅ Pasa | alta, lectura, edición del monto, borrado y 404 después |
| Importación de gastos | ✅ Pasa | 3 gastos importados en un lote y encontrados en el listado |
| Presupuesto con alerta al pasar el umbral | ✅ Pasa | presupuesto de $100 al 80%: gasto de $90 → alerta al 90.0% |
| Regla recurrente que genera su movimiento | ✅ Pasa | regla con cargo hoy: 1 movimiento y siguiente cargo 2026-11-20; segunda corrida, ninguno nuevo (CP-08 y CP-09) |
| Meta de ahorro con avance | ✅ Pasa | meta de $1,000 con $250 iniciales: $250 ahorrados, avance del 25% |
| Costo proyectado contra gasto real | ✅ Pasa | a la fecha $26,500.00 proyectado contra $11,675.00 real; futuro aparte $31,600.00 |
| Panel principal | ✅ Pasa | ingresos $18,000.00, gastos $4,017.00, proyectado $9,500.00 = /projected/monthly |
| Movimiento en dólares | ⏳ Pendiente | el tipo de cambio de USD aún no se ha consultado (defecto 36) |
| Exportación de datos | ✅ Pasa | archivo descargable con 193 gastos, igual que el listado |
| Recurrentes del mes | ✅ Pasa | lo que cobran las reglas en el mes: $0.00 (defecto 30; 30 días) |

**Movimiento en dólares, pendiente:** hasta el 13/11 producción solo tenía MXN
(defecto 36). La migración 015 agregó USD y EUR, y el tipo de cambio real llega
con el trabajo diario de las 06:00 UTC del 15/11, ya con la llave configurada
en Railway. Se vuelve a correr después de esa hora.

## En el navegador

Flujos que necesitan el correo, el archivo descargado o la pantalla real.

| Flujo | Resultado | Fecha | Evidencia |
|---|---|---|---|
| Registro con aceptación del aviso, confirmación por correo e inicio de sesión (CP-01) | Pendiente | | Captura del correo y del primer acceso |
| Eliminar la cuenta | Pendiente | | Captura antes y después; la cuenta ya no inicia sesión |
| Reporte PDF del mes (RF12, CP-12) | Pendiente | | El PDF descargado, comparado contra la API en `docs/verificacion-RF12.md` |
| Las once pantallas en un teléfono (CP-14) | Pendiente | | Una captura por pantalla |
