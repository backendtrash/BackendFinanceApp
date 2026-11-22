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
| CP-10 (pantalla) | Con la cuenta B, las gráficas muestran su mensaje de vacío, sin error | mensajes: ['No expenses this month']; errores de la página: 0 | ✅ Pasa | `capturas/cp10-vacio-dashboard.png, cp10-vacio-analytics.jpg` |
| 4.2 Aislamiento en el navegador | En las once pantallas, B no ve ningún dato de A | A ve sus datos en 10 pantallas (dashboard, expenses, earnings, weeks, budgets, recurring, projected, goals, categories, analytics); B ve datos de A en 0 | ✅ Pasa | `capturas/aislamiento-*.jpg` (22) |
| CP-06 (pantalla) | Al borrar una categoría en uso, se impide y la pantalla explica por qué | la categoría sigue: True; la pantalla explica el motivo: False; error no manejado en la página: Request failed with status code 409 | ❌ Falla | `capturas/cp06-borrar-categoria-en-uso.jpg` |
| CP-13 (formulario) | Con el token vencido, se renueva y el formulario se envía sin perder datos | 401 simulado: 1; renovaciones del token: 1; categoría guardada con el nombre escrito: True | ✅ Pasa | `capturas/cp13-token-vencido.jpg` |
| CP-14 (emulado) | Las once pantallas en un teléfono, legibles y sin desbordamiento horizontal | tamaño de iPhone 13 (390×844), emulado: desbordan 0 | ✅ Pasa | `capturas/`capturas/cp14-movil-*.jpg` (11) |

**CP-06 falla: defecto 38.** La API impide el borrado (la categoría sigue),
pero la pantalla no dice por qué: el 409 queda como error sin manejar en la
página. La captura muestra además "0 system defaults": en producción no había
categorías predefinidas (defecto 39).

## Pendientes

| Caso | Por qué queda pendiente |
|---|---|
| CP-01 | Necesita un correo real: registrarse, recibir la confirmación y entrar |
| CP-14 en un teléfono real | La corrida fue emulada; la Evidencia 2 pide un dispositivo real |

## Resumen al 22/11

| | Corridos | Pasan | Fallan | Pendientes |
|---|---|---|---|---|
| Por la API | 10 | 9 | 1 (CP-11, defecto 37) | — |
| En el navegador | 5 | 4 | 1 (CP-06, defecto 38) | — |
| A mano | 1 (CP-12, el 14/11) | 1 | — | 2 (CP-01; CP-14 en un teléfono real) |
