# Acta de decisión — cálculos de analítica (defectos 7 a 10)

> **BORRADOR, sin firmar.** Este documento prepara la decisión; no la toma.
> Hasta que el coach lo firme, las cuatro pruebas siguen como `xfail` en
> `tests/test_analytics_calcs.py` y el código no se toca.

**Proyecto:** BackendFinance · **Hito:** H3 (23/10/2026) · **Riesgo:** R4
**Preparada:** 18/10/2026

Cada cálculo devuelve hoy un valor que no coincide con lo que la pantalla
dice mostrar. La prueba de cada uno ya fija el valor que *creemos* correcto;
falta que el coach confirme cuál es, porque cambiar estos números cambia lo
que el usuario ya ve.

---

### Defecto 7 — Patrimonio neto (`get_net_worth_history`)

| | |
|---|---|
| **Hoy** | Suma solo los meses de la ventana pedida y arranca en 0. Con 50 000 ahorrados hace años y un mes plano, muestra 0. |
| **Propuesta** | Patrimonio acumulado desde el primer movimiento hasta el fin de cada mes. Con el ejemplo, 50 000. |
| **Alternativa** | Mantener la suma por ventana, pero renombrar la pantalla a "Cambio neto del periodo". |

Decisión: ☐ Propuesta  ☐ Alternativa  ☐ Otra: ______________________

### Defecto 8 — Tendencias por categoría (`get_spending_trends`)

| | |
|---|---|
| **Hoy** | El promedio cuenta como 0 los meses en que la categoría no existía. Una categoría nueva con 500 en su único mes completo promedia 125, y el mes actual (otros 500) aparece como +300 %, tendencia "sube", con un gasto que es plano. |
| **Propuesta** | Promediar solo los meses en que la categoría tuvo movimientos. Con el ejemplo, 500 y tendencia "estable". |
| **Alternativa** | Promediar desde que se creó la categoría, contando como 0 los meses sin gasto a partir de entonces. |

Decisión: ☐ Propuesta  ☐ Alternativa  ☐ Otra: ______________________

### Defecto 9 — Varianza proyectada (`get_projected_analytics`)

| | |
|---|---|
| **Hoy** | Resta el gasto real de 3 meses pasados al proyectado de 6 meses (pasados y futuros). Con 100/mes proyectado y nada gastado, reporta −600. |
| **Propuesta** | Comparar solo los meses ya transcurridos. Con el ejemplo, −300. |
| **Alternativa** | Quitar la varianza total de la respuesta y dejar solo la varianza por mes. |

Decisión: ☐ Propuesta  ☐ Alternativa  ☐ Otra: ______________________

### Defecto 10 — Vista semanal vs. mensual (`get_dashboard_weekly`)

| | |
|---|---|
| **Hoy** | Un costo semanal sin día asignado se suma completo en cada semana: 500/semana da 2 500 en un mes de 5 semanas, mientras el total mensual dice 2 166.67. |
| **Propuesta** | Repartir el costo para que las semanas del mes sumen lo mismo que el total mensual (500 × 4.333 = 2 166.67). |
| **Alternativa** | Contar el costo una vez por semana calendario y cambiar el total mensual para que use el mismo criterio. |

Decisión: ☐ Propuesta  ☐ Alternativa  ☐ Otra: ______________________

---

**Efecto de firmar:** por cada defecto se ajusta el cálculo, la prueba deja
de ser `xfail` y pasa a ser una prueba normal, y `docs/defects.md` registra
la fecha de cierre y el commit.

&nbsp;

Coach: ______________________________  Fecha: ____ / ____ / 2026

Equipo: _____________________________  Fecha: ____ / ____ / 2026
