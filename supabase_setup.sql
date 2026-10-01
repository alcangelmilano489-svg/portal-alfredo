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

create table if not exists public.comentarios (
    id uuid primary key default gen_random_uuid(),
    publicacion_id text not null references public.publicaciones(id) on delete cascade,
    nombre text not null default 'Visitante' check (char_length(nombre) <= 80),
    texto text not null check (char_length(texto) between 1 and 1000),
    created_at timestamptz not null default now()
);

alter table public.comentarios enable row level security;

drop policy if exists "Comentarios visibles para visitantes"
    on public.comentarios;
create policy "Comentarios visibles para visitantes"
    on public.comentarios
    for select
    to anon, authenticated
    using (true);

grant select on public.comentarios to anon, authenticated;
grant all on public.comentarios to service_role;

create index if not exists comentarios_publicacion_fecha_idx
    on public.comentarios (publicacion_id, created_at);

create table if not exists public.suscriptores (
    id uuid primary key default gen_random_uuid(),
    email text not null unique check (char_length(email) <= 254),
    created_at timestamptz not null default now()
);

alter table public.suscriptores enable row level security;
grant all on public.suscriptores to service_role;

create index if not exists suscriptores_created_at_idx
    on public.suscriptores (created_at);

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