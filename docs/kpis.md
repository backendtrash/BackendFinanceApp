# KPIs por corte

Una fila por corte. La fila de cada corte se llena **después** de correr la
suite completa ese día, con los números que salen de esa corrida.

| Corte | VP | VG | Horas reales | IAC | RF verificados | CRV | DSA | ACP |
|---|---|---|---|---|---|---|---|---|
| 11/10/2026 | 75 | 84.8 | 75 | 1.13 | 7 de 12 | 58.3% | 1 | 100% |
| 18/10/2026 | 90 | | | | | | | |

## Datos de la suite al 18/10/2026

Para llenar la fila del 18/10:

```
pytest (PR #2 + PR #3 combinados)   ->  219 passed, 1 skipped, 4 xfailed
test_isolation.py contra staging    ->  24 passed
```

- **Skipped (1):** `tests/test_isolation.py` en la suite normal, que corre
  sin credenciales. **Sí se ejecutó** aparte, el 18/10, contra staging con
  dos cuentas reales: 24 passed. La primera corrida encontró los defectos 18
  a 21; ninguno fue una fuga de datos.
- **Xfailed (4):** los defectos de analítica 7 a 10, a la espera del acta
  del coach (`docs/decisiones/`).
- **Defectos** (de `docs/defects.md`): 21 registrados; 15 corregidos, 6
  abiertos (7–10, 15, 16). El 6 está verificado en staging y pendiente de
  desplegar en producción.
