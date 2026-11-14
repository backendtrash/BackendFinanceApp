# Verificación de las cinco gráficas esenciales (paquete 3.4)

**Fecha:** 13/11/2026 · **Cuenta:** `prueba-a` · **Contra:** producción

Las cinco gráficas esenciales de la tabla 6 del diseño, comparadas contra las
filas de la propia cuenta. `scripts/verificar_graficas.py` lee todos los gastos
e ingresos por la API, recalcula cada cifra desde esas filas y la pone junto a
la que devuelve el endpoint de la gráfica. Cualquier diferencia aparece como ❌.

**Datos de prueba.** `scripts/seed_prueba_a.py` cargó el 13/11 un año de
movimientos: 204 movimientos en 12 meses, tres categorías, un presupuesto con
alerta, una regla recurrente, una meta y dos costos proyectados, todo marcado
`[seed-h4]`. Con eso se cubre también el volumen del caso CP-11.

## Resultado

Cuenta de prueba, November 2026. 193 gastos y 12 ingresos leídos.

| Gráfica | Cifra | Desde las filas | API | |
|---|---|---|---|---|
| 1. Tarjetas | Ingresos del mes | 18,000.00 | 18,000.00 | ✅ |
| 1. Tarjetas | Gastos del mes | 4,017.00 | 4,017.00 | ✅ |
| 1. Tarjetas | Balance | 13,983.00 | 13,983.00 | ✅ |
| 1. Tarjetas | Proyectado (= /projected/monthly) | 9,500.00 | 9,500.00 | ✅ |
| 2. Dona | Comida [seed-h4] | 2,105.00 | 2,105.00 | ✅ |
| 2. Dona | Servicios [seed-h4] | 1,287.00 | 1,287.00 | ✅ |
| 2. Dona | Transporte [seed-h4] | 625.00 | 625.00 | ✅ |
| 2. Dona | Suma de categorías = gastos del mes | 4,017.00 | 4,017.00 | ✅ |
| 3. Ingresos vs gastos | Jun 2026 gastos | 3,728.00 | 3,728.00 | ✅ |
| 3. Ingresos vs gastos | Jun 2026 ingresos | 18,000.00 | 18,000.00 | ✅ |
| 3. Ingresos vs gastos | Jul 2026 gastos | 3,854.00 | 3,854.00 | ✅ |
| 3. Ingresos vs gastos | Jul 2026 ingresos | 18,000.00 | 18,000.00 | ✅ |
| 3. Ingresos vs gastos | Aug 2026 gastos | 3,710.00 | 3,710.00 | ✅ |
| 3. Ingresos vs gastos | Aug 2026 ingresos | 18,000.00 | 18,000.00 | ✅ |
| 3. Ingresos vs gastos | Sep 2026 gastos | 3,868.00 | 3,868.00 | ✅ |
| 3. Ingresos vs gastos | Sep 2026 ingresos | 18,000.00 | 18,000.00 | ✅ |
| 3. Ingresos vs gastos | Oct 2026 gastos | 3,790.00 | 3,790.00 | ✅ |
| 3. Ingresos vs gastos | Oct 2026 ingresos | 18,000.00 | 18,000.00 | ✅ |
| 3. Ingresos vs gastos | Nov 2026 gastos | 4,017.00 | 4,017.00 | ✅ |
| 3. Ingresos vs gastos | Nov 2026 ingresos | 18,000.00 | 18,000.00 | ✅ |
| 4. Presupuestos | Comida [seed-h4]: gastado | 2,105.00 | 2,105.00 | ✅ |
| 4. Presupuestos | Comida [seed-h4]: % usado | 105.25 | 105.25 | ✅ |
| 5. Flujo semanal | W1 (Nov 01) gastos | 1,330.00 | 1,330.00 | ✅ |
| 5. Flujo semanal | W2 (Nov 08) gastos | 2,687.00 | 2,687.00 | ✅ |
| 5. Flujo semanal | W3 (Nov 15) gastos | 0.00 | 0.00 | ✅ |
| 5. Flujo semanal | W4 (Nov 22) gastos | 0.00 | 0.00 | ✅ |
| 5. Flujo semanal | W5 (Nov 29) gastos | 0.00 | 0.00 | ✅ |
| 5. Flujo semanal | Suma de semanas proyectadas = mes | 9,500.00 | 9,500.00 | ✅ |

**Todo cuadra**.

## Pantallas

Las cifras de la API son las que pinta el frontend: cada gráfica lee
directamente su endpoint. Capturas del 14/11 con estos datos:
`evidencia/panel-2026-11.png` (tarjetas, ingresos contra gastos, dona,
flujo semanal y avance de presupuestos) y `evidencia/analisis-2026-11.png`.
Las cifras visibles coinciden con la tabla: gastos del mes $4,017.00, Comida
$2,105.00 al 105.3%, proyectado $9,500.00.
