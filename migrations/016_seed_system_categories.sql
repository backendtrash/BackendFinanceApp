-- ══════════════════════════════════════════════════════════════════════════
-- Predefined categories (defect 39)
-- Run once in the Supabase SQL editor. Idempotent — a category that already
-- exists as a system category (same name and type) is left untouched.
--
-- RF04 asks for "un catálogo de categorías predefinidas, comunes a todos los
-- usuarios". 002 created the table and its policies, with system rows marked
-- by a null user_id, but no migration ever inserted one: in production every
-- user started with no categories at all.
--
-- System rows are read-only through the API: every write filters on the
-- caller's user_id, which never matches null, and the policies allow
-- inserting, updating and deleting only one's own rows.
-- ══════════════════════════════════════════════════════════════════════════

insert into public.categories (user_id, name, color, icon, type)
select null, c.name, c.color, 'tag', c.type::public.transaction_type
  from (values
    ('Alimentos',        '#E07A5F', 'expense'),
    ('Transporte',       '#3D405B', 'expense'),
    ('Vivienda',         '#81B29A', 'expense'),
    ('Servicios',        '#F2CC8F', 'expense'),
    ('Salud',            '#E63946', 'expense'),
    ('Entretenimiento',  '#9B5DE5', 'expense'),
    ('Educación',        '#00BBF9', 'expense'),
    ('Ropa',             '#F15BB5', 'expense'),
    ('Otros gastos',     '#6B7280', 'expense'),
    ('Sueldo',           '#2A9D8F', 'income'),
    ('Honorarios',       '#43AA8B', 'income'),
    ('Inversiones',      '#277DA1', 'income'),
    ('Otros ingresos',   '#6B7280', 'income')
  ) as c(name, color, type)
 where not exists (
   select 1 from public.categories e
    where e.user_id is null and e.name = c.name and e.type = c.type::public.transaction_type
 );
