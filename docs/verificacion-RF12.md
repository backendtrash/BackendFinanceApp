# Revisión de RF12 contra E1 (acción AP-5)

**Fecha:** 14/11/2026 · **Contra:** E1, *Documento de Especificación de
Requerimientos*, v1.0 del 18/09/2026 · **Cuenta:** `prueba-a`, noviembre de
2026, con los datos de `scripts/seed_prueba_a.py`

> RF-12. Debe permitir generar y descargar un reporte mensual en formato PDF
> con el resumen de movimientos, totales por categoría y avance de
> presupuestos.

RF12 se verifica en el frontend, porque ahí se genera el reporte (Actividad
3, reglas comunes de medición). El reporte se descargó desde Panel → *PDF
Report* y cada cifra se comparó contra la API del mismo mes.

## Frase por frase

| Frase de E1 | En el reporte (`evidencia/reporte-pdf-2026-11.pdf`) | Contra la API | Resultado |
|---|---|---|---|
| Generar y descargar un reporte | Botón *PDF Report* del Panel; descarga `budget-report-2026-11.pdf`, dos páginas | — | ✅ |
| Mensual | "November 2026", generado el 14/11/2026 | — | ✅ |
| Resumen de movimientos | Ingresos $18,000.00 · gastos $4,017.00 · balance $13,983.00 · ahorro 77.7% | `/analytics/dashboard`: las mismas cuatro cifras | ✅ |
| | Tabla de gastos: 16 movimientos que suman $4,017.00; tabla de ingresos: 1, $18,000.00 | Los 16 gastos y el ingreso de noviembre de la cuenta | ✅ |
| Totales por categoría | Comida $2,105.00 (52.4%) · Servicios $1,287.00 (32.0%) · Transporte $625.00 (15.6%) | `/analytics/categories`: iguales | ✅ |
| Avance de presupuestos | Comida: $2,105.00 de $2,000.00, 105.3%, OVER | `/analytics/budget-progress`: $2,105.00, 105.25% | ✅ |

El reporte también trae el avance de las metas, que E1 no pide.

## Resultado

**RF12 verificado el 14/11/2026.** Las cifras del reporte son las mismas que
muestra el Panel (`evidencia/panel-2026-11.png`) y las mismas que la API, que
a su vez cuadran contra las filas de la cuenta
(`verificacion-graficas.md`).

## Notas

- La tabla de movimientos pide hasta 200 por mes. Un mes con más de 200
  gastos saldría cortado en la tabla, aunque los totales seguirían siendo
  correctos porque vienen del Panel. Para una cuenta personal es poco
  probable; queda anotado en `defects.md`, en "Smaller things".
