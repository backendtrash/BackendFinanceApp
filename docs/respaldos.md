# Respaldos de producción (AP-8)

El plan gratuito de Supabase no hace respaldos automáticos. El workflow
`.github/workflows/backup.yml` los hace cada domingo a las 09:00 UTC (03:00 en
Juárez), y también se puede lanzar a mano.

## Qué hace cada respaldo

1. Respalda el esquema `public` (todos los datos de la app) y `auth.users`,
   que hace falta porque todas las tablas de usuario la referencian.
2. Lo **cifra** con AES-256 y la frase de `BACKUP_PASSPHRASE`.
3. **Comprueba que se puede restaurar**: lo descifra en la misma ejecución, lee
   su índice y falla si falta alguna tabla. Un respaldo que nunca se ha
   probado no cuenta como respaldo.
4. Lo guarda como artefacto de la ejecución durante **90 días**.

**Por qué va cifrado:** el repositorio es público, y cualquier usuario de
GitHub con sesión iniciada puede descargar los artefactos de un repositorio
público. Sin la frase, el archivo no se puede leer.

**Si se pierde la frase, se pierden los respaldos.** Guárdala fuera del
repositorio, por ejemplo en un gestor de contraseñas.

## Configuración (una vez)

En GitHub → Settings → Secrets and variables → Actions:

| Secret | Valor |
|---|---|
| `SUPABASE_DB_URL` | Supabase → **Connect** → *Session pooler* → la URI, con la contraseña de la base puesta. No uses la conexión directa: en el plan gratuito solo funciona por IPv6, y los servidores de GitHub no tienen IPv6. |
| `BACKUP_PASSPHRASE` | Una frase larga que elijas tú. |

## Restaurar

1. GitHub → **Actions** → *backup* → la ejecución que quieras → **Artifacts**
   → descarga el `.zip` y extrae `backendfinance-AAAA-MM-DD.dump.gpg`.
2. Descifra:
   ```bash
   gpg --decrypt backendfinance-AAAA-MM-DD.dump.gpg > backendfinance.dump
   ```
3. Revisa qué contiene antes de tocar nada:
   ```bash
   pg_restore --list backendfinance.dump
   ```
4. Restaura sobre una base que ya tenga las migraciones aplicadas. Primero
   `auth.users`, porque las demás tablas apuntan a ella, y después los datos:
   ```bash
   pg_restore --data-only --no-owner --table=users --schema=auth \
     --dbname="$URL_DESTINO" backendfinance.dump
   pg_restore --data-only --no-owner --schema=public \
     --disable-triggers --dbname="$URL_DESTINO" backendfinance.dump
   ```

Necesitas un cliente de PostgreSQL de la **misma versión mayor** que el
servidor, o más nueva.

**Nunca restaures sobre producción sin un respaldo reciente de su estado
actual.** Restaurar reemplaza datos.

## Verificación del esquema (E7)

`.github/workflows/schema-check.yml` aplica `migrations/` sobre una base vacía
y compara su esquema con el de producción. Sale en rojo si difieren. Su
artefacto `schema-e7` contiene el esquema de producción (solo la estructura,
sin datos) y la diferencia, como evidencia de E7.
