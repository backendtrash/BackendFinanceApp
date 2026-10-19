## Qué cambia y por qué

<!-- Qué problema resuelve. Si cierra un defecto, su número en docs/defects.md. -->

## Lista

- [ ] **Cliente del usuario.** El código nuevo que consulta la base de datos usa `db()`, no `supabase_admin`. El cliente de sistema solo vive en `app/scheduler.py`.
- [ ] **Filtra por `user_id`.** Toda consulta sobre datos de un usuario lleva `.eq("user_id", ...)`, aunque las políticas por fila ya apliquen.
- [ ] **Agregué una prueba** que falla sin este cambio y pasa con él.
- [ ] **Actualicé `docs/defects.md`** si este PR encuentra o cierra un defecto, con la fecha del día.
- [ ] `pytest` en verde en local.

## Cómo se probó

<!-- Comandos y resultado. Para la API: qué endpoint, con qué cuenta. -->
