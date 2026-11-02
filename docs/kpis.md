# KPIs por corte

Una fila por corte. La fila de cada corte se llena **después** de correr la
suite completa ese día, con los números que salen de esa corrida.

| Corte | VP | VG | Horas reales | IAC | RF verificados | CRV | DSA | ACP |
|---|---|---|---|---|---|---|---|---|
| ~~11/10/2026~~ (original, reemplazada) | 75 | 84.8 | 75 | 1.13 | 7 de 12 | 58.3% | 1 | 100% |
| 11/10/2026 corregido | 75 | — | 75 | 0.80 | 0 de 12 | 0% | 2 | 100% |
| 18/10/2026 | 90 | 92.8 | 90 | 1.03 | 8 de 12 | 66.7% | 0 | 100% |
| 25/10/2026 | 105 | 109.2 | 105 | 1.04 | 9 de 12 | 75% | 0 | 100% |
| 01/11/2026 | 120 | 116 | 120 | 0.97 | 11 de 12 | 91.7% | 0 | 100% |

### Contra las metas

| KPI | 11/10 corregido | 18/10 | 25/10 | 01/11 | Meta |
|---|---|---|---|---|---|
| P1. IAC | 0.80 | 1.03 (92.8 ÷ 90) | 1.04 | 0.97 (116 ÷ 120) | ≥ 0.95 ✅ |
| P2. CRV | 0% | 66.7% (8 de 12) | 75% (9 de 12) | 91.7% (11 de 12) | 50% en H3 ✅ |
| Q1. DSA | 2 | 0 | 0 | 0 | 0 ✅ |
| Q2. ACP | 100% | 100% | 100% | 100% (H1, H2, H3) | 100% ✅ |

- **25/10:** valores del seguimiento de ese corte (IAC 1.04, 9 de 12); el
  VG de 109.2 h sale de 1.04 × 105.
- **01/11:** con los defectos 7 a 10 cerrados por el acta firmada, RF09 y
  RF10 cuentan como verificados y el paquete 3.2 queda completo: VG 116 h
  contra 120 planeadas. Solo falta RF12, que se verifica en el frontend
  antes de H4. La revisión de RF09 y RF10 contra su texto completo en E1
  (AP-5) está pendiente.
- **ACP:** H3 se aprobó a la primera el 23/10 (`docs/hitos/acta-H3.pdf`).
- **El acta de H3 trae otras cifras para el 18/10** (IAC 0.98 y 58.3%). La
  medición vigente es la de esta tabla; el acta se preparó con una anterior.

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

## Datos de la suite al 01/11/2026

Base de la fila del 01/11, sobre lo que estaba en `main` al cierre del día
(PR #21, #22 y front #7 integrados):

```
pytest                               ->  345 passed, 1 skipped, 0 xfailed
test_isolation.py en el CI de main   ->  verde (25 casos, contra producción)
```

- **Xfailed (0):** los defectos 7 a 10 están cerrados con el acta firmada
  (`docs/decisiones/acta-analitica.pdf`); sus pruebas ya son pruebas normales.
- **Skipped (1):** `tests/test_isolation.py` en la suite normal, sin
  credenciales. Corre en el CI de cada PR y de `main`, donde falla si faltan.
- **Producción, 01/11:** defecto 10 con un costo de prueba de $500 por
  semana: $2,214.29 en las cuatro vistas de diciembre. Defectos 7 y 8:
  patrimonio y tendencias cuadran con las filas de `prueba-a`.
- **Defectos** (de `docs/defects.md`): 30 registrados; 29 corregidos,
  1 abierto (30, severidad baja).
