# Revisión de RF09 y RF10 contra E1 (acción AP-5)

**Fecha:** 02/11/2026 · **Contra:** E1, *Documento de Especificación de
Requerimientos*, v1.0 del 18/09/2026, firmado en H1 · **Estado del código:**
`main` en `14a9ee4` (corte del 01/11)

Cada frase del requerimiento se revisó por separado: dónde se implementa, qué
prueba la cubre y qué se vio en producción con la cuenta de prueba.

**Criterio de verificado** (Actividad 3, reglas comunes de medición): la
funcionalidad responde solo con autenticación, pasa sus pruebas automatizadas
(incluida la de aislamiento con dos cuentas) y no tiene defectos abiertos que
alteren su resultado.

## RF09. Costos proyectados — **verificado**

> Debe permitir registrar costos futuros estimados por categoría y mes, así
> como consultar el total proyectado de un mes determinado y compararlo
> posteriormente contra el gasto real, sin que estos registros afecten los
> saldos efectivos.

| Frase de E1 | Dónde | Prueba | En producción (01/11) |
|---|---|---|---|
| Registrar costos estimados por categoría y mes | `POST /projected/` (categoría; mensual, semanal o de una vez con mes y año) | aislamiento (crear, listar, editar ajeno) | Costo de $500/semana creado y borrado |
| Consultar el total proyectado de un mes | `GET /projected/monthly` con la regla de `app/projection.py` | `test_projection.py`, `test_the_dashboard_card_and_the_weekly_view_agree` | $2,214.29 en diciembre, el ejemplo del acta |
| Compararlo contra el gasto real | `GET /analytics/projected` (defecto 9) | `test_projected_total_variance_compares_like_with_like` | Proyectado y real a la fecha, futuro aparte |
| Sin afectar los saldos efectivos | El módulo no escribe en `expenses` ni en `earnings` | — (revisión de código) | Con el costo "Pago" activo, no aparece en los gastos del mes |

Sin defectos abiertos que alteren su resultado.

## RF10. Analítica y reportes — **verificado el 02/11** (no verificado al corte del 01/11)

> Debe presentar tarjetas de resumen del mes en curso, la comparación mensual
> de ingresos contra gastos, el flujo de efectivo semanal, la distribución del
> gasto por categoría, la comparación entre gasto proyectado y real, el avance
> de todos los presupuestos, la evolución acumulada del patrimonio neto, la
> comparación del mes actual contra el mismo mes del año anterior y la
> tendencia de gasto por categoría, además de permitir el arrastre del saldo
> de un mes al siguiente de forma idempotente.

| Frase de E1 | Endpoint · pantalla | Prueba de cálculo | Resultado |
|---|---|---|---|
| Tarjetas de resumen del mes | `/analytics/dashboard` · Panel | `test_dashboard_*` (8) y aislamiento | ✅ |
| Ingresos contra gastos por mes | `/analytics/monthly` · Panel y Análisis | **ninguna** | ⚠️ sin prueba |
| Flujo de efectivo semanal | `/analytics/weekly`, `/dashboard-weekly` · Análisis y Panel | solo la parte proyectada (`test_projection.py`) | ⚠️ ingresos y gastos por semana sin prueba |
| Distribución por categoría | `/analytics/categories` · Panel y Análisis | **ninguna** | ⚠️ sin prueba |
| Proyectado contra real | `/analytics/projected` · Análisis y Plan | defecto 9 | ✅ |
| Avance de todos los presupuestos | `/analytics/budget-progress` · Panel, Análisis | **ninguna** | ⚠️ sin prueba |
| Evolución acumulada del patrimonio | `/analytics/net-worth` · Análisis | defecto 7 | ❌ **defecto 31** |
| Mes actual contra el mismo mes del año anterior | `/analytics/year-over-year` · Análisis | **ninguna** | ⚠️ sin prueba |
| Tendencia de gasto por categoría | `/analytics/trends` · Análisis | defecto 8 | ❌ **defecto 31** |
| Arrastre del saldo, idempotente | `/analytics/carry-forward` · Panel | **ninguna** | ❌ **defecto 31** |

La prueba de aislamiento con dos cuentas cubre solo `/analytics/dashboard`;
los otros nueve endpoints de RF10 no tienen caso de aislamiento.

### Por qué no cuenta como verificado

1. **Defecto 31 (abierto).** El arrastre se guarda como un gasto o un ingreso
   real con fecha del día 1 del mes siguiente. Ese movimiento vuelve a
   sumarse en el patrimonio acumulado, en los totales de varios meses, en la
   tendencia por categoría y en el gasto real de proyectado contra real. En
   `prueba-a` el único gasto real es de $145 (19/10), pero el patrimonio dice
   −$290, y bajará otros $145 cada mes sin gastar nada.
2. **Pruebas que faltan.** Cinco de las diez funciones no tienen ninguna
   prueba de cálculo y el arrastre no tiene prueba de idempotencia. El
   criterio pide que la funcionalidad pase sus pruebas automatizadas; para
   esas partes no existen.

### Qué hace falta para verificarlo (antes de H4, 08/11)

- Corregir el defecto 31: que el arrastre no cuente dos veces el mismo
  dinero. Cómo mostrarlo (solo como saldo inicial del mes, o como
  movimiento marcado y excluido de la analítica) es una decisión de producto.
- Pruebas de cálculo para las cinco funciones sin cubrir y de idempotencia
  del arrastre, incluidas dos llamadas simultáneas.
- Casos de aislamiento para los endpoints de analítica que faltan.

## Efecto en los indicadores

RF10 contaba como verificado en la fila del 01/11 de `kpis.md`. Con esta
revisión deja de contar: la fila **01/11 corregido (02/11)** queda en 10 de
12 RF (83.3%), VG 112.4 h e IAC 0.94.

## Seguimiento del 02/11: RF10 verificado

Lo que faltaba quedó en `main` el 02/11 (PR #25 y front PR #8):

| Hallazgo | Qué se hizo | Evidencia |
|---|---|---|
| Defecto 31 | El arrastre es el saldo inicial del mes, calculado y nunca guardado; la migración 014 quitó los arrastres guardados | `test_carry_forward.py` (5); producción: patrimonio −$145, era −$290 |
| Cinco funciones sin prueba de cálculo | Pruebas con valores conocidos | `test_analytics_rf10.py` (8) |
| Arrastre sin prueba de idempotencia | Ya no escribe nada; dos llamadas no cambian ninguna fila | `test_applying_writes_nothing_however_often_it_is_called` |
| Aislamiento solo en el panel | Diez rutas de analítica más | `test_isolation.py`, verde en el CI del PR y de `main` |

| Frase de E1 | Resultado |
|---|---|
| Ingresos contra gastos por mes · flujo semanal · por categoría · avance de presupuestos · mismo mes del año anterior | ✅ |
| Evolución del patrimonio · tendencia por categoría · arrastre idempotente | ✅ |

RF10 cumple el criterio desde el 02/11. Cuenta para el siguiente corte; la
fila del 01/11 se queda como se midió.
