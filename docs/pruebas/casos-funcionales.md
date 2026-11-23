# Casos funcionales (paquete 4.1)

**Fecha de ejecución:** 22/11/2026 · **Contra:** producción, con `prueba-a` y `prueba-b`

## Por la API

`scripts/casos_prueba.py` corre los casos de la Evidencia 2 que pasan por la
API, con el resultado esperado tal como está escrito ahí. Lo que crea queda
marcado `[cp]` y se borra al terminar cada caso.

| Caso | Resultado esperado (Evidencia 2) | Resultado obtenido | Estado |
|---|---|---|---|
| CP-02 | Sin sesión, la ruta de gastos redirige al acceso y la API responde 401 | la API responde 401 sin sesión (la redirección de la pantalla es manual) | ✅ Pasa |
| CP-03 | Gasto de 100 dólares: se guarda el monto original y su equivalente en pesos | monto original US$100.00 y equivalente $1912.41 MXN al tipo de cambio 19.124116 (actualizado 2026-11-22) | ✅ Pasa |
| CP-04 | Gasto negativo: 422 con un mensaje que identifica el campo | 422 y el detalle señala el campo `body.amount` | ✅ Pasa |
| CP-05 | A pide por id un gasto de B: responde como si no existiera | la cuenta A pide un gasto de B por su id: 404, sin ningún dato de B | ✅ Pasa |
| CP-06 | Borrar una categoría con gastos: se impide y se explica | 409: "{'message': 'This category still has movements. Reassign or delete them before removing th" | ✅ Pasa |
| CP-07 | Presupuesto de $5,000 al 80%, gastos por $4,100: alerta en el historial | gastos por $4,100 de $5,000: alerta registrada en el historial al 82.0% | ✅ Pasa |
| CP-08 y CP-09 | La regla genera su movimiento y avanza un mes; repetir no genera otro | CP-08: 1 movimiento y siguiente cargo el 2026-12-22. CP-09: la segunda corrida no generó ninguno | ✅ Pasa |
| CP-10 | Usuario sin movimientos: las gráficas responden vacías, sin error | cuenta sin movimientos (B): las 8 consultas de analítica responden 200 con totales en cero | ✅ Pasa |
| CP-11 | 200 movimientos en 12 meses: comparación anual en menos de 500 ms y totales correctos | Fail: 193 gastos en doce meses; comparación anual: media 515 ms, p90 569 ms en 20 llamadas (la red sola, 45 ms); total del mes $4,017.00 igual a la suma de las filas | ❌ Falla |
| CP-13 | Con el token vencido, se renueva de forma transparente | la API entrega un token nuevo con el de renovación y lo acepta (la parte del formulario es manual) | ✅ Pasa |

**CP-11 falla: defecto 37.** La comparación anual tarda en promedio más de
500 ms con 200 movimientos. La red hasta el servidor son unos 45 ms; el resto
es del servidor. Medido con 30 llamadas a las 14:00: media de 599 ms (p90 de
690 ms), y el panel 671 ms.

## En el navegador

`scripts/pruebas_navegador.py` maneja un Chromium real (Playwright) contra el
frontend publicado, con las dos cuentas de prueba. El 401 de CP-13 se simula
respondiendo 401 una vez a la petición del formulario, que es lo que el
navegador recibe cuando el token vence. CP-14 se corrió en el tamaño de un
iPhone 13, emulado.

| Caso | Resultado esperado | Resultado obtenido | Estado | Evidencia |
|---|---|---|---|---|
| CP-02 (pantalla) | Sin sesión, la dirección de gastos lleva a la pantalla de acceso | /expenses terminó en /login | ✅ Pasa | `capturas/cp02-sin-sesion.jpg` |
| CP-10 (pantalla) | Con la cuenta B, las gráficas muestran su mensaje de vacío, sin error | mensajes: ['No expenses this month']; errores de la página: 0 | ✅ Pasa | `capturas/cp10-vacio-dashboard.jpg`, `capturas/cp10-vacio-analytics.jpg` |
| 4.2 Aislamiento en el navegador | En las once pantallas, B no ve ningún dato de A | A ve sus datos en 10 pantallas (dashboard, expenses, earnings, weeks, budgets, recurring, projected, goals, categories, analytics); B ve datos de A en 0 | ✅ Pasa | `capturas/aislamiento-*.jpg` (22) |
| CP-06 (pantalla) | Al borrar una categoría en uso, se impide y la pantalla explica por qué | la categoría sigue: True; la pantalla explica el motivo: False; error no manejado en la página: Request failed with status code 409 | ❌ Falla | `capturas/cp06-borrar-categoria-en-uso.jpg` |
| CP-13 (formulario) | Con el token vencido, se renueva y el formulario se envía sin perder datos | 401 simulado: 1; renovaciones del token: 1; categoría guardada con el nombre escrito: True | ✅ Pasa | `capturas/cp13-token-vencido.jpg` |
| CP-14 (emulado) | Las once pantallas en un teléfono, legibles y sin desbordamiento horizontal | tamaño de iPhone 13 (390×844), emulado: desbordan 0 | ✅ Pasa | `capturas/`capturas/cp14-movil-*.jpg` (11) |

**CP-06 falló a las 14:30: defecto 38.** La API impedía el borrado, pero la
pantalla no decía por qué. Su captura mostraba además "0 system defaults": en
producción no había categorías predefinidas (defecto 39). Con las dos
correcciones desplegadas (front PR #13 y migración 016), la corrida de las
15:20 dio:

| Caso | Resultado esperado | Resultado obtenido | Estado | Evidencia |
|---|---|---|---|---|
| CP-06 (pantalla) | Al borrar una categoría en uso, se impide y la pantalla explica por qué | la categoría sigue: True; la pantalla explica el motivo: True | ✅ Pasa | `capturas/cp06-borrar-categoria-en-uso.jpg` |

Las capturas de `capturas/` son las de esa segunda corrida; las cinco pruebas
de navegador y la de aislamiento pasaron.

## A mano, con correo y teléfono reales

| Caso | Fecha | Resultado esperado | Resultado obtenido | Estado | Evidencia |
|---|---|---|---|---|---|
| CP-01 | 22/11/2026 | Se crea la cuenta aceptando el aviso, llega el correo de confirmación y el enlace abre la sesión | Cuenta nueva con el aviso aceptado; el correo de Supabase llegó a las 21:26; con la cuenta confirmada, el Panel abre con sesión | ✅ Pasa | `capturas/cp01-1-registro.jpg`, `cp01-2-correo-confirmacion.jpg`, `cp01-3-sesion-iniciada.jpg` |
| CP-14 | 22/11/2026 | Las once pantallas en un teléfono real, legibles y operables, sin desbordamiento horizontal | iPhone, navegador del teléfono: las once pantallas se leen completas y ninguna se desplaza de lado | ✅ Pasa | `capturas/cp14-telefono-01-dashboard.jpg` a `-11-settings.jpg` |

El correo de la cuenta está difuminado en las capturas. Observación sin defecto:
el correo de confirmación usa la plantilla genérica de Supabase, sin el nombre
de BackendFinance.

## Resumen al 22/11

**Los 14 casos de la Evidencia 2 están ejecutados: 13 pasan y CP-11 falla**
(defecto 37, en corrección dentro de 4.4). Con eso el paquete 4.1 entrega
sus resultados completos.

| | Corridos | Pasan | Fallan | Pendientes |
|---|---|---|---|---|
| Por la API | 10 | 9 | 1 (CP-11, defecto 37; repetido a las 15:20) | — |
| En el navegador | 5 | 5 (CP-06 tras corregir el defecto 38) | — | — |
| A mano | 3 (CP-12 el 14/11; CP-01 y CP-14 el 22/11) | 3 | — | — |

**CP-11 repetido a las 15:20**, después de cambiar la región del servidor:

| Caso | Resultado esperado (Evidencia 2) | Resultado obtenido | Estado |
|---|---|---|---|
| CP-11 | 200 movimientos en 12 meses: comparación anual en menos de 500 ms y totales correctos | Fail: 193 gastos en doce meses; comparación anual: media 677 ms, p90 802 ms en 20 llamadas (la red sola, 160 ms); total del mes $4,017.00 igual a la suma de las filas | ❌ Falla |
