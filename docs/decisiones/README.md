# Decisiones

Actas firmadas que deciden algo que el código no puede decidir solo.

| Archivo | Decide | Estado |
|---|---|---|
| `acta-analitica.pdf` | El valor correcto de los cálculos de analítica, defectos 7 a 10 | Firmada. Opción A en los cuatro |

## Fechas del acta de analítica

| Qué | Fecha |
|---|---|
| Emitida (según el acta) | 18/10/2026 |
| Decisión y revisión con el coach, en H3 | 23/10/2026 |
| Fecha escrita junto a la firma | 23/10/2026 |
| Foto de la página firmada recibida | 27/10/2026 |
| Entra al repositorio | 01/11/2026 |

El PDF son las páginas del acta con las decisiones marcadas; su última
página es la foto de la página firmada. La foto se guardó sin sus metadatos
de cámara.

## Cómo se usa

1. Lo que el código no puede decidir solo se presenta al coach como acta,
   con las opciones, un ejemplo de cada una y una recomendación.
2. El coach marca una opción y firma. El acta firmada se guarda aquí.
3. Solo entonces se cierra el defecto. Su prueba en
   `tests/test_analytics_calcs.py` deja de ser `xfail`, y `docs/defects.md`
   registra el cierre con la fecha en que el acta entra al repositorio y el
   commit de la corrección.

Las pruebas `xfail` llevan `raises=AssertionError`: solo cuentan como fallo
esperado si falla la aserción del defecto, y no cualquier otro error.

Las actas de los puntos de control están en `docs/hitos/`.
