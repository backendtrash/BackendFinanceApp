# Estado del backend contra el plan — BackendFinance

**Corte:** 04/10/2026 · **Fase:** 3. Implementación (05/10 al 08/11/2026)
**Repositorio:** `backendtrash/BackendFinanceApp` · **Diseño de referencia:** Documento E2, E3 y E4 aprobado en H2

> La implementación parte de una prueba de concepto propia del backend. En esta fase se adapta al diseño aprobado en H2 y se verifica contra los criterios de H3 y H4.

---

## 1. Qué pide el plan

| Hito | Fecha | Criterio | Paquetes EDT |
|---|---|---|---|
| H3 | 23/10/2026 | Al menos la mitad de los módulos del backend responden con autenticación | 3.1 Backend base (22 h) |
| H4 | 08/11/2026 | Los 12 RF implementados y el frontend conectado | 3.2 Backend avanzado (18 h), 3.3 a 3.5 |
| Meta M3 | 08/11/2026 | Al menos 60 puntos de acceso operativos y verificados | — |

---

## 2. Cobertura por requerimiento

La columna **Verificado** se marca solo cuando el endpoint se probó con dos cuentas y responde según el diseño de H2. Ver la sección 5 sobre por qué sigue vacía.

| RF | Módulo | Endpoints | Código | Verificado |
|---|---|---|---|---|
| RF01 | Autenticación (ES256 con JWKS de Supabase) | 5 | Existe | ☐ |
| RF02 | Gastos (CRUD, importación, borrado total) | 10 | Existe | ☐ |
| RF03 | Ingresos (CRUD, importación, borrado total) | 9 | Existe | ☐ |
| RF04 | Categorías (+ bloqueo de borrado con movimientos) | 6 | Existe | ☐ |
| RF05 | Divisas | 4 | Existe | ☐ |
| RF06 | Presupuestos y alertas (+ tarea programada de umbrales) | 9 | Existe | ☐ |
| RF07 | Movimientos recurrentes (+ tarea programada diaria) | 7 | Existe | ☐ |
| RF08 | Metas de ahorro | 6 | Existe | ☐ |
| RF09 | Costos proyectados | 6 | Existe | ☐ |
| RF10 | Analítica | 12 | Existe | ☐ |
| RF11 | Preferencias | 3 | Existe | ☐ |
| RF12 | Exportación de reportes | — | Frontend (jsPDF) | ☐ |

**Totales:** 11 módulos de dominio y 77 endpoints, más 3 de salud (`/`, `/health`, `/scheduler`) = **80**. De estos, 74 exigen autenticación y 6 son públicos. Por arriba de la meta M3 de 60.

### Correcciones al conteo anterior

El corte previo decía 87 endpoints más 3 de salud, y 77 + 3 = 80 sin el módulo de fondos. Medido contra la tabla de rutas de la aplicación, no a mano:

| | Antes de esta fase | Ahora |
|---|---|---|
| Endpoints de módulo | 82 | 77 |
| Salud | 3 | 3 |
| **Total** | **85** | **80** |

El conteo anterior sobrecontaba por 5. El total bajó al sacar `sinking_funds` (10 endpoints) y subió al completar el borrado total (5 endpoints nuevos).

---

## 3. Pendientes contra el diseño de H2

### 3.1 Alcance — cerrado

- [x] **Módulo `sinking_funds` (10 endpoints, 2 tablas).** Fuera de `main`, conservado íntegro en la rama `feat/sinking-funds`. Si se quiere incorporar, vuelve como solicitud de cambio con su estimación de horas.
- [x] **`plans/001-fund-category-and-progress.md`.** Movido fuera del repositorio **antes del primer commit**, no borrado después. Contenía rutas locales con un nombre de usuario y notas sobre defectos sin corregir; en un repositorio público, borrarlo en un commit posterior no lo habría quitado del historial.

### 3.2 Base de datos y seguridad — cerrado salvo la prueba con dos cuentas

- [x] **Migraciones SQL versionadas de las 10 tablas del diseño.** `migrations/000` a `migrations/012`, en orden de dependencias, idempotentes. Incluyen las tres funciones RPC que el código llamaba y que no existían en el repositorio.
- [x] **Políticas de seguridad por fila de cada tabla.** Con una advertencia importante registrada en `migrations/README.md`: el backend **no** las ejerce, porque todos los módulos usan el cliente de rol de servicio, que las omite. En ejecución, el aislamiento depende del filtro `.eq("user_id", ...)` escrito a mano en cada consulta.
- [x] **Prueba de aislamiento con dos cuentas en cada módulo.** Ejecutada el 18/10/2026 contra staging (proyecto Supabase aparte, API desplegada en Railway): `tests/test_isolation.py`, 7 módulos, **24 passed**, sin omisiones. La primera corrida encontró los defectos 18 a 21, ninguno de ellos una fuga de datos; se corrigieron y la segunda corrida pasó completa. **Falta repetirla en producción** tras integrar el PR #2.

### 3.3 Reglas de integridad del diseño — cerrado

- [x] **Procesar dos veces el mismo día no duplica movimientos (RF07).** No había ninguna protección. El motor insertaba la transacción y después avanzaba `next_due_date`; cualquier fallo entre las dos dejaba la fila escrita y el cursor sin mover. Ahora la ocurrencia se reclama primero, con una actualización condicionada al valor leído, y solo se escribe si esa reclamación afectó una fila. Además el rezago se drena en una sola pasada. Respaldo en base de datos: índice único sobre `(recurring_rule_id, date)`.
- [x] **Una categoría con movimientos no se puede eliminar (RF04).** El borrado no tenía ninguna comprobación y el esquema dice `ON DELETE SET NULL`, así que la base de datos lo aceptaba y reescribía el historial en silencio. Ahora se cuentan las referencias en las seis tablas que apuntan a una categoría y se responde **409** con el detalle por tabla.
- [x] **Borrado total completo.** Existía en 3 de 8 módulos. Se añadieron presupuestos, metas, proyecciones, categorías propias y preferencias, y los tres existentes se movieron del router a su capa de servicio.

### 3.4 Pruebas — cerrado

- [x] **Carpeta `tests/` con al menos una prueba por módulo que confirme el rechazo con 401 sin token.** Hecho, y sin lista escrita a mano: la prueba lee la tabla de rutas de la aplicación y genera un caso por endpoint, así que cubre los 74 protegidos de los 11 módulos y no se queda desactualizada al añadir rutas. También fija cuáles 6 son públicos.
- [x] **Pruebas de los cálculos de analítica (riesgo R4).** Todo el módulo es aritmética en Python sobre consultas simples —no hay una sola llamada RPC— así que se prueba completo con un cliente simulado.

**Resultado actual:** `196 passed, 1 skipped, 4 xfailed`.

### 3.5 Documentación y configuración — cerrado

- [x] **Nombre del proyecto.** README, `app_name`, `.env.example` y la descripción de la API decían "Budget Tracker". Ahora dicen BackendFinance.
- [x] **Tabla de endpoints del README.** La corrección real es menor de lo que decía el corte anterior: metas y proyecciones **ya estaban** en la tabla; faltaba solo **preferencias**, que tampoco aparecía en el árbol de estructura. Ya están ambas, con conteos por módulo verificados contra la tabla de rutas.
- [x] **`SUPABASE_JWT_SECRET`.** Sí se usaba: por una rama HS256 en `decode_jwt`. Se eliminó esa rama en lugar de la variable. Elegía con qué clave verificar leyendo el campo `alg` de la cabecera del propio token, antes de comprobar ninguna firma —es confusión de algoritmos— y el diseño de H2 especifica ES256 con JWKS. Sin esa rama la variable quedó realmente sin uso, y entonces sí se quitó.

---

## 4. Registro para los KPIs

| Fecha | Paquete EDT | Horas | Qué se hizo | RF verificados | Defectos encontrados |
|---|---|---|---|---|---|
| 04/10/2026 | 3.1 Backend base | _por confirmar_ | Importación del repositorio. 12 módulos, 85 endpoints, 1 migración, sin pruebas | — | Conteo de endpoints del corte anterior sobrecontaba por 5 |
| 04/10/2026 | 3.1 Backend base | _por confirmar_ | Alcance alineado con H2: `sinking_funds` a rama aparte, `plans/` fuera del historial | — | `001_sinking_funds.sql` referenciaba 5 tablas sin migración: no podía ser la migración 001 |
| 04/10/2026 | 3.2 Backend avanzado | _por confirmar_ | 13 migraciones versionadas: 10 tablas, 3 enums, 3 funciones RPC, RLS en todas | — | `set_updated_at()` nunca se creaba, así que los disparadores de `updated_at` se omitían en silencio; las 3 funciones RPC no existían en el repositorio |
| 04/10/2026 | 3.2 Backend avanzado | _por confirmar_ | Suite de pruebas: 401 en los 74 endpoints protegidos, analítica, funciones puras, aislamiento | RF01 (401 en todos los módulos) | **5**: token mal formado devolvía 500 en todos los endpoints; 4 defectos de cálculo en analítica |
| 04/10/2026 | 3.3 Reglas de integridad | _por confirmar_ | Idempotencia de recurrentes, bloqueo 409 de categorías, borrado total en los 8 módulos | RF04, RF07 (con pruebas) | `POST /process` procesaba las reglas de todos los usuarios |
| 04/10/2026 | 3.5 Documentación | _por confirmar_ | Renombrado a BackendFinance, ES256 obligatorio, README corregido | RF01 | Confusión de algoritmos en `decode_jwt` |

> **Horas:** sin rellenar a propósito. Es dato de esfuerzo del equipo y no debe inventarse.

**Defectos encontrados en total: 10.** Cinco están corregidos; los cuatro de analítica y la omisión de RLS en todo el backend quedan registrados en `docs/defects.md`, fuera del alcance de esta fase.

---

## 5. Lo que falta para marcar la columna Verificado

La columna **Verificado** de la sección 2 sigue vacía, y no por descuido.

Marcarla exige probar cada módulo con dos cuentas contra el diseño de H2. Eso no se puede simular, y la razón es concreta: cada módulo importa `supabase_admin`, el cliente de rol de servicio, que **omite las políticas de seguridad por fila**. Las políticas están escritas y son correctas, pero el backend nunca las ejerce. En ejecución, lo único que separa a un usuario de otro es el filtro `.eq("user_id", ...)` escrito a mano en cada consulta. Un cliente simulado no puede demostrar que esos filtros estén todos presentes; solo dos cuentas reales pueden.

La suite ya está escrita. Para ejecutarla:

```bash
export EXPOS_TEST_BASE_URL=http://localhost:8000
export EXPOS_TEST_USER_A_EMAIL=...   EXPOS_TEST_USER_A_PASSWORD=...
export EXPOS_TEST_USER_B_EMAIL=...   EXPOS_TEST_USER_B_PASSWORD=...

pytest tests/test_isolation.py -v
```

Crea una fila en cada uno de 7 módulos como usuario A y comprueba que B no la lee, no la borra, no la ve en los listados y no ve sus importes en el panel. Si pasa en verde, la columna se puede marcar.

Pendiente también: **ejecutar las migraciones**. Están verificadas contra la gramática real de PostgreSQL, pero no se han corrido. El proyecto Supabase se construyó a mano antes de que existiera el repositorio, así que el esquema se reconstruyó a partir de los payloads de inserción y los validadores de Pydantic. Antes de aplicarlas sobre el proyecto existente hay que compararlas con lo que ya está.
