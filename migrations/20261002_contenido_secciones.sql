create table if not exists public.contenido_secciones (
    seccion text primary key check (seccion in ('vida', 'obra')),
    contenido text not null default '',
    updated_at timestamptz not null default now()
);

alter table public.contenido_secciones enable row level security;

drop policy if exists "Contenido editorial visible para visitantes"
    on public.contenido_secciones;
create policy "Contenido editorial visible para visitantes"
    on public.contenido_secciones
    for select
    to anon, authenticated
    using (true);

revoke all on table public.contenido_secciones from public, anon, authenticated;
grant select on public.contenido_secciones to anon, authenticated;
grant all on public.contenido_secciones to service_role;

do $$
begin
    if exists (
        select 1
        from pg_publication
        where pubname = 'supabase_realtime'
    ) and not exists (
        select 1
        from pg_publication_tables
        where pubname = 'supabase_realtime'
          and schemaname = 'public'
          and tablename = 'contenido_secciones'
    ) then
        execute 'alter publication supabase_realtime add table public.contenido_secciones';
    end if;
end;
$$;
