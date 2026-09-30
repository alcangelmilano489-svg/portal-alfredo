create extension if not exists pgcrypto;

create table if not exists public.publicaciones (
    id uuid primary key default gen_random_uuid(),
    titulo text not null default '',
    texto text not null default '',
    "mediaUrl" text,
    "mediaType" text,
    "mediaPath" text,
    seccion text not null default 'inicio'
        check (seccion in ('inicio', 'fotos', 'videos')),
    fecha timestamptz not null default now()
);

alter table public.publicaciones
    add column if not exists titulo text not null default '',
    add column if not exists texto text not null default '',
    add column if not exists "mediaUrl" text,
    add column if not exists "mediaType" text,
    add column if not exists "mediaPath" text,
    add column if not exists seccion text default 'inicio',
    add column if not exists fecha timestamptz default now();

update public.publicaciones
set seccion = 'inicio'
where seccion is null;

alter table public.publicaciones
    alter column seccion set default 'inicio',
    alter column seccion set not null,
    enable row level security;

drop policy if exists "Publicaciones visibles para visitantes"
    on public.publicaciones;
create policy "Publicaciones visibles para visitantes"
    on public.publicaciones
    for select
    to anon, authenticated
    using (true);

create index if not exists publicaciones_seccion_fecha_idx
    on public.publicaciones (seccion, fecha desc);

insert into storage.buckets (id, name, public)
values ('media', 'media', true)
on conflict (id) do update set public = true;

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
          and tablename = 'publicaciones'
    ) then
        execute 'alter publication supabase_realtime add table public.publicaciones';
    end if;
end;
$$;