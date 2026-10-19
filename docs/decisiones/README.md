# Decisiones

Actas firmadas que deciden algo que el código no puede decidir solo.

| Archivo | Decide | Estado |
|---|---|---|
| `acta-analitica-BORRADOR.md` | El valor correcto de los cálculos de analítica, defectos 7 a 10 | Borrador, sin firmar |

## Cómo se usa

1. El borrador se imprime o se comparte con el coach.
2. El coach marca una opción por defecto y firma.
3. La versión firmada se guarda aquí como PDF o foto, con la fecha en el
   nombre: `acta-analitica-2026-10-DD.pdf`.
4. Solo entonces se toca el código. Por cada defecto decidido, la prueba de
   `tests/test_analytics_calcs.py` deja de ser `xfail` y `docs/defects.md`
   registra el cierre con su fecha y su commit.

Los valores "Hoy" de cada acta están medidos ejecutando las funciones, no
estimados. Las pruebas `xfail` llevan `raises=AssertionError`: solo cuentan
como fallo esperado si falla la aserción del defecto, y no cualquier otro
error.
