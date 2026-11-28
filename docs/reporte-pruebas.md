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

| Participante | Tareas completadas | Promedio (preguntas 1 a 8) |
|---|---|---|
| *Pendiente de los resultados* | | |

**Promedio general:** *pendiente* · **Criterio de H5:** 4.0 o más.

**Comentarios** (tal como los escribieron):

- *Pendiente*

## 4. Defectos de la fase

| # | Defecto | Severidad | Estado |
|---|---|---|---|
| 36 | Producción solo tenía MXN; no se podía registrar en otra divisa | Media | Corregido (22/11) |
| 37 | La comparación anual y el panel tardaban más de 500 ms en el servidor | Media | Corrección en revisión (PR #38): un solo pool de conexiones a la base |
| 38 | Borrar una categoría en uso no decía por qué | Baja | Corregido (22/11) |
| 39 | En producción no había categorías predefinidas | Media | Corregido (22/11) |

**Defectos de severidad alta abiertos: 0.**

## 5. Conclusión para H5

| Condición de H5 | Estado |
|---|---|
| Todos los casos de prueba ejecutados | ✅ 14 de 14 |
| Sin defectos críticos abiertos | ✅ 0 altos; 1 medio (37) en corrección |
| Aislamiento verificado | ✅ 36 de 36 y las once pantallas |
| Satisfacción de 4.0 o más | *Pendiente de los resultados de la encuesta* |
