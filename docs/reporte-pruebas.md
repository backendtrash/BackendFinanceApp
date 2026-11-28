# Reporte de pruebas (E8)

**Proyecto:** BackendFinance, plataforma web de finanzas personales para Studio A
**Fase:** 4. Pruebas · del 14/11 (aprobación de H4) al 28/11/2026 (H5)
**Para:** la revisión de H5 con el coach empresarial

El detalle de cada caso, con su evidencia, está en `docs/pruebas/`. Este
reporte resume sus tres partes: pruebas funcionales, aislamiento y aceptación.

---

## 1. Pruebas funcionales (paquete 4.1)

Los catorce casos de la Evidencia 2, ejecutados contra producción. Cada uno
se corrió por la vía que su resultado esperado pide: la API, un navegador real
o a mano con correo y teléfono reales.

| Caso | Qué prueba | Resultado esperado | Resultado obtenido | Estado |
|---|---|---|---|---|
| CP-01 | Registro (RF01) | Cuenta creada aceptando el aviso, correo de confirmación, sesión iniciada | Correo recibido; con la cuenta confirmada, el Panel abre | ✅ |
| CP-02 | Sesión (RNF-02) | Sin sesión: la pantalla lleva al acceso y la API responde 401 | Las dos cosas | ✅ |
| CP-03 | Divisas (RF02, RF05) | Gasto de US$100: monto original y su equivalente en pesos | US$100 → $1,912.41 al tipo de cambio del día | ✅ |
| CP-04 | Validación (RF02) | Monto negativo: 422 que nombra el campo | 422 en `amount` | ✅ |
| CP-05 | Confidencialidad (RNF-01) | A pide un gasto de B: como si no existiera | 404, sin datos de B | ✅ |
| CP-06 | Categorías (RF04) | Borrar una categoría con gastos: se impide y se explica | Se impide y la pantalla dice por qué (tras corregir el defecto 38) | ✅ |
| CP-07 | Presupuestos (RF06) | Presupuesto de $5,000 al 80%, gastos por $4,100: alerta | Alerta al 82% en el historial | ✅ |
| CP-08 | Recurrentes (RF07) | La regla genera su movimiento y avanza un mes | 1 movimiento; siguiente cargo un mes después | ✅ |
| CP-09 | Recurrentes (RF07) | Repetir la tarea no genera otro | Ninguno nuevo | ✅ |
| CP-10 | Analítica sin datos (RF10) | Gráficas vacías con su mensaje, sin error | Mensajes de vacío; 8 consultas en 200 | ✅ |
| CP-11 | Analítica con volumen (RF10, RNF-03) | 200 movimientos: comparación anual en menos de 500 ms, totales correctos | Totales correctos; 515–677 ms de media | ❌ Defecto 37 |
| CP-12 | Reporte PDF (RF12) | El PDF muestra los mismos totales que el Panel | Iguales en todas sus cifras | ✅ |
| CP-13 | Renovación de sesión (RNF-02) | Con el token vencido, el formulario se envía sin perder datos | Renovado en silencio; guardado con lo escrito | ✅ |
| CP-14 | Móvil (RNF-06) | Las once pantallas en un teléfono real, sin desbordamiento | iPhone: legibles, ninguna se desplaza de lado | ✅ |

**Resultado: 13 de 14 pasan.** CP-11 falla por tiempo; su corrección está en
la sección 4.

Además de los catorce casos, la suite automática corre en cada cambio: 372
pruebas, incluidas desde el 28/11 las de CP-03, CP-04 y CP-07.

## 2. Pruebas de aislamiento (paquete 4.2)

| Corrida | Resultado |
|---|---|
| `test_isolation.py` contra la API publicada en Railway, con dos cuentas reales (22/11) | **36 de 36** |
| La misma suite en el CI, con la API levantada del código de `main` y la base de producción (22/11) | **36 de 36** |
| Las once pantallas en un navegador real, con cada cuenta, una captura por pantalla (22/11) | La cuenta B no ve ningún dato de la cuenta A en ninguna |

La prueba de aislamiento es obligatoria en cada pull request: ningún cambio
entra si falla.

## 3. Pruebas de aceptación (paquete 4.3)

**Sesiones:** 25 y 26/11/2026, con el guion de seis tareas
(`docs/pruebas/guion-aceptacion.md`) y la encuesta de satisfacción de 1 a 5.

Cinco participantes. Cada calificación es el promedio de un participante en
la encuesta de 1 a 5; el orden de la tabla no corresponde al de las
sesiones.

| Participante | Calificación | Observación |
|---|---|---|
| 1 | 5.0 | |
| 2 | 5.0 | |
| 3 | 5.0 | |
| 4 | 5.0 | |
| 5 | 3.9 | Faltaba un tutorial de uso (defecto 40) |

**Promedio general: 4.78** ((4 × 5.0 + 3.9) / 5) · **Criterio de H5:** 4.0 o
más: **se cumple.**

Las tareas completadas por participante no se registraron en los
resultados entregados; no se reportan.

**Comentarios** (tal como los escribieron):

- "La plataforma me permite ver mis gastos y me ayudan a ahorrar."
- "Las gráficas me permiten ahorrar tiempo de mi vida y planear mis inversiones."

## 4. Defectos de la fase

| # | Defecto | Severidad | Estado |
|---|---|---|---|
| 36 | Producción solo tenía MXN; no se podía registrar en otra divisa | Media | Corregido (22/11) |
| 37 | La comparación anual y el panel tardaban más de 500 ms en el servidor | Media | Abierto. Pool de conexiones integrado (PR #38): de 610 a 406 ms en el servidor, todavía 631 ms desde fuera. Consultas en paralelo en revisión (PR #44) |
| 38 | Borrar una categoría en uso no decía por qué | Baja | Corregido (22/11) |
| 39 | En producción no había categorías predefinidas | Media | Corregido (22/11) |
| 40 | No había tutorial de uso dentro de la aplicación (aceptación) | Baja | Enlace al manual en revisión (front PR #14) |

**Defectos de severidad alta abiertos: 0.**

## 5. Conclusión para H5

| Condición de H5 | Estado |
|---|---|
| Todos los casos de prueba ejecutados | ✅ 14 de 14 |
| Sin defectos críticos abiertos | ✅ 0 altos; abiertos 1 medio (37) y 1 bajo (40), ambos en corrección |
| Aislamiento verificado | ✅ 36 de 36 y las once pantallas |
| Satisfacción de 4.0 o más | ✅ 4.78 de 5, cinco participantes |
