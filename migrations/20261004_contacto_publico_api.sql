create table if not exists public.contacto_publico (
    id smallint primary key default 1 check (id = 1),
    whatsapp text not null default '' check (char_length(whatsapp) <= 32),
    email text not null default '' check (char_length(email) <= 254),
    messenger_url text not null default '' check (char_length(messenger_url) <= 2048),
    tiktok_handle text not null default '' check (char_length(tiktok_handle) <= 24),
    updated_at timestamptz not null default now()
);

alter table public.contacto_publico enable row level security;
drop policy if exists "Permitir actualizacion administrativa de contacto" on public.contacto_publico;
revoke all on table public.contacto_publico from anon, authenticated;
grant select on table public.contacto_publico to anon, authenticated;
grant all on table public.contacto_publico to service_role;

do $$
begin
    if not exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename = 'contacto_publico'
          and policyname = 'contacto_publico_read'
    ) then
        create policy contacto_publico_read
            on public.contacto_publico
            for select
            to anon, authenticated
            using (true);
    end if;
end
$$;

do $$
begin
    if exists (select 1 from pg_publication where pubname = 'supabase_realtime')
       and not exists (
           select 1 from pg_publication_tables
           where pubname = 'supabase_realtime'
             and schemaname = 'public'
             and tablename = 'contacto_publico'
       ) then
        execute 'alter publication supabase_realtime add table public.contacto_publico';
    end if;
end
$$;
