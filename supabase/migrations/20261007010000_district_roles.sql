-- Lakad: who may see which district's tickets. Supabase holds sign-in and these roles only. The tickets live in
-- SQLite on the Lakad server, which checks every dashboard request against the caller's row here.
--
-- Three roles: a District 1 analyst, a District 2 analyst, and a citywide analyst who sees both districts (and any
-- ticket that falls in neither). The Lakad server reads the caller's row using the caller's own token, so Supabase
-- verifies the token and RLS returns that one row: no row means no access.
--
--   an analyst (signed in, role authenticated)   reads their own row and the district names, writes nothing
--   anyone else (publishable key alone, anon)    nothing
--   an admin (SQL editor, Supabase dashboard)    adds, changes and removes analysts; nobody can change their own role

-- Makati after the EMBO ruling: 23 barangays, 20 in District 1 (west) and 3 in District 2 (east).
create table public.districts (
  id smallint primary key,
  name text not null unique
);
insert into public.districts (id, name) values
  (1, 'District 1 (Western Makati)'),
  (2, 'District 2 (Eastern Makati)');

create table public.analysts (
  user_id uuid primary key references auth.users (id) on delete cascade,
  district_id smallint references public.districts (id),
  citywide boolean not null default false,
  name text not null default '',
  created_at timestamptz not null default now(),
  constraint one_scope check (citywide = (district_id is null))  -- one district, or the whole city: never both, never neither
);

-- RLS on both tables. Supabase grants anon and authenticated everything on new tables in public, and policies do not
-- take that back, so revoke it all and grant back reading only.
alter table public.districts enable row level security;
alter table public.analysts enable row level security;

revoke all on public.districts, public.analysts from anon, authenticated;
grant select on public.districts, public.analysts to authenticated;

create policy "districts: signed-in users read the list" on public.districts
  for select to authenticated using (true);

-- (select auth.uid()) runs once per query instead of once per row.
create policy "analysts: read your own row" on public.analysts
  for select to authenticated using (user_id = (select auth.uid()));
