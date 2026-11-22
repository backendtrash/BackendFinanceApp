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

## Manuales

| Caso | Fecha | Resultado esperado | Resultado obtenido | Estado | Evidencia |
|---|---|---|---|---|---|
| CP-01 | | Se crea la cuenta, llega el correo de confirmación y el enlace abre la sesión | | Pendiente | |
| CP-02 (pantalla) | | Sin sesión, la dirección de gastos lleva a la pantalla de acceso | | Pendiente | |
| CP-06 (pantalla) | | Al borrar una categoría en uso, la pantalla explica por qué no se puede | | Pendiente | |
| CP-10 (pantalla) | | Con la cuenta B, las gráficas muestran su mensaje de vacío | | Pendiente | |
| CP-12 | 14/11/2026 | El PDF muestra los mismos totales que el Panel | Iguales en todas sus cifras | ✅ Pasa | `docs/verificacion-RF12.md` |
| CP-13 (formulario) | | Con el token vencido, el formulario se envía sin perder datos | | Pendiente | |
| CP-14 | | Las once pantallas en un teléfono, legibles y sin desbordamiento | | Pendiente | Una captura por pantalla |

## Resumen al 22/11

- **Por la API:** 10 casos, 9 pasan y 1 falla (CP-11, defecto 37).
- **Manuales:** 1 hecho (CP-12); 6 pendientes de hacer en el navegador y el teléfono.
