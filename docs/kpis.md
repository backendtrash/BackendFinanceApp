# KPIs por corte

Una fila por corte. La fila de cada corte se llena **después** de correr la
suite completa ese día, con los números que salen de esa corrida.

| Corte | VP | VG | Horas reales | IAC | RF verificados | CRV | DSA | ACP |
|---|---|---|---|---|---|---|---|---|
| ~~11/10/2026~~ (original, reemplazada) | 75 | 84.8 | 75 | 1.13 | 7 de 12 | 58.3% | 1 | 100% |
| 11/10/2026 corregido | 75 | — | 75 | 0.80 | 0 de 12 | 0% | 2 | 100% |
| 18/10/2026 | 90 | 92.8 | 90 | 1.03 | 8 de 12 | 66.7% | 0 | 100% |

### Contra las metas

| KPI | 11/10 corregido | 18/10 | Meta |
|---|---|---|---|
| P1. IAC | 0.80 | 1.03 (92.8 ÷ 90) | ≥ 0.95 ✅ |
| P2. CRV | 0% | 66.7% (8 de 12) | 50% en H3 ✅ |
| Q1. DSA | 2 | 0 | 0 ✅ |
| Q2. ACP | 100% | 100% | 100% ✅ |

### Por qué se corrigió la fila del 11/10

- **CRV, de 58.3% a 0%.** Un RF solo cuenta como verificado cuando pasó la
  prueba con dos cuentas. El 11/10 esa prueba existía pero nunca se había
  ejecutado, así que ningún RF podía contar. La primera corrida fue el 18/10.
- **DSA, de 1 a 2.** El 11/10 había dos defectos de severidad alta sin
  atender, no uno: el 6 (la API no aplicaba las políticas por fila) y el 11
  (el tipo de cambio guardaba `"now()"` como fecha), que se vio ese día y
  después se clasificó como alta.
- **IAC, de 1.13 a 0.80.** Recalculado en la revisión del corte.

## Datos de la suite al 18/10/2026

Base de la fila del 18/10, sobre lo que estaba en `main` al cierre del día:

```
pytest                               ->  219 passed, 1 skipped, 4 xfailed
test_isolation.py contra staging     ->  24 passed
```

(Con lo integrado el 19/10 —defectos 15, 16 y 24— la suite sube a 234;
eso cuenta para el corte del 25/10.)

- **Skipped (1):** `tests/test_isolation.py` en la suite normal, que corre
  sin credenciales. **Sí se ejecutó** aparte, el 18/10, contra staging con
  dos cuentas reales: 24 passed. La primera corrida encontró los defectos 18
  a 21; ninguno fue una fuga de datos.
- **Xfailed (4):** los defectos de analítica 7 a 10, a la espera del acta
  del coach (`docs/decisiones/`).
- **Defectos** (de `docs/defects.md`): 24 registrados; 20 corregidos, 4
  abiertos (7–10, a la espera del acta).
- **CI:** hasta el defecto 22, el workflow nunca llegó a ejecutar una prueba
  (fallaba al arrancar). Los runs anteriores a ese arreglo no son evidencia.
