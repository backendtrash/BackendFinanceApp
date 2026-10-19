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
pytest  ->  209 passed, 1 skipped, 4 xfailed
```

- **Skipped (1):** `tests/test_isolation.py`, la prueba con dos cuentas.
  Sigue sin ejecutarse: necesita un proyecto Supabase y dos cuentas reales.
  Mientras no corra, ningún RF nuevo pasa a verificado por esta vía.
- **Xfailed (4):** los defectos de analítica 7 a 10, a la espera del acta
  del coach (`docs/decisiones/`).
- **Defectos** (de `docs/defects.md`): 17 registrados; 11 corregidos, 6
  abiertos (7–10, 15, 16). El 6 está corregido en código pero sin desplegar.
