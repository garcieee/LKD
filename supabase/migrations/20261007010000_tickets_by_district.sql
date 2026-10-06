-- Lakad: tickets by district, behind row level security.
--
-- Who can do what:
--   the Lakad server (secret key, role service_role; it bypasses RLS)   writes tickets and sightings, reads status changes
--   an analyst (signed in, role authenticated)                          reads the tickets of their own district, changes their status
--   anyone else (publishable key alone, role anon)                      nothing; the public map comes from the Lakad server
--
-- An analyst belongs to one district, through a row in public.analysts that only an admin can write. Every policy
-- compares a row's district with that row, so deleting it takes access away at once, with no token left to expire.
-- A ticket with no district (outside both, e.g. an EMBO barangay that is now Taguig) is seen by no analyst.

-- 1. Districts. Makati after the EMBO ruling: 23 barangays, 20 in District 1 (west) and 3 in District 2 (east).
create table public.districts (
  id smallint primary key,
  name text not null unique
);
insert into public.districts (id, name) values
  (1, 'District 1 (Western Makati)'),
  (2, 'District 2 (Eastern Makati)');

-- 2. Analysts: which district each signed-in person may see.
create table public.analysts (
  user_id uuid primary key references auth.users (id) on delete cascade,
  district_id smallint not null references public.districts (id),
  name text not null default '',
  created_at timestamptz not null default now()
);

-- 3. Tickets: one per hazard. id is the id of the hazard's first report, so links to /reports/<id> keep working.
create table public.tickets (
  id text primary key,
  category text not null check (category in
    ('pothole', 'open_manhole', 'flooded_drain', 'broken_streetlight', 'blocked_sidewalk', 'other', 'sos')),
  status text not null default 'open' check (status in ('open', 'verified', 'assigned', 'fixed', 'rejected')),
  district_id smallint references public.districts (id),
  lat double precision not null check (lat between -90 and 90),
  lng double precision not null check (lng between -180 and 180),
  priority real not null default 0 check (priority between 0 and 100),
  band text not null default 'Low' check (band in ('Critical', 'High', 'Medium', 'Low')),
  breakdown jsonb not null default '{}',  -- why it ranks where it does (models/tickets/types.py Breakdown) and flags
  reporters integer not null default 1 check (reporters >= 1),
  note text not null default '',
  photo_url text not null default '',
  video_url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  fixed_at timestamptz
);
create index tickets_district_priority on public.tickets (district_id, priority desc);
create index tickets_updated_at on public.tickets (updated_at);  -- the server pulls status changes in this order

-- 4. Sightings: every report that joined a ticket, each with its own photo.
create table public.sightings (
  id text primary key,  -- the report id
  ticket_id text not null references public.tickets (id) on delete cascade,
  lat double precision not null,
  lng double precision not null,
  accuracy_m real,
  note text not null default '',
  photo_url text not null default '',
  video_url text,
  created_at timestamptz not null default now()
);
create index sightings_ticket on public.sightings (ticket_id);

-- 5. Ticket events: who changed a status, from what, to what, when. Written only by the trigger below.
create table public.ticket_events (
  id bigint generated always as identity primary key,
  ticket_id text not null references public.tickets (id) on delete cascade,
  actor uuid,  -- the analyst; null when the server made the change. No foreign key, so the record outlives the account.
  from_status text,
  to_status text not null,
  at timestamptz not null default now()
);
create index ticket_events_ticket on public.ticket_events (ticket_id);

-- 6. Status bookkeeping, whoever changes the status. In a schema the Data API does not expose, with a pinned
-- search_path, because it runs with its owner's rights (it has to write ticket_events, which nobody else may).
create schema if not exists private;
revoke all on schema private from public;

create function private.ticket_updated() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  new.updated_at := now();
  if new.status is distinct from old.status then
    new.fixed_at := case
      when new.status = 'fixed' then now()
      when new.status = 'open' then null  -- reopened
      else old.fixed_at
    end;
    insert into public.ticket_events (ticket_id, actor, from_status, to_status)
    values (new.id, (select auth.uid()), old.status, new.status);
  end if;
  return new;
end $$;
revoke all on function private.ticket_updated() from public;

create trigger ticket_updated before update on public.tickets
  for each row execute function private.ticket_updated();

-- 7. Row level security on every table. Supabase grants anon and authenticated everything on new tables in public
-- and policies do not take that back, so revoke it all, then grant back the least each role needs.
alter table public.districts enable row level security;
alter table public.analysts enable row level security;
alter table public.tickets enable row level security;
alter table public.sightings enable row level security;
alter table public.ticket_events enable row level security;

revoke all on public.districts, public.analysts, public.tickets, public.sightings, public.ticket_events
  from anon, authenticated;
revoke all on sequence public.ticket_events_id_seq from anon, authenticated;
grant select on public.districts, public.analysts, public.tickets, public.sightings, public.ticket_events
  to authenticated;
grant update (status) on public.tickets to authenticated;  -- the one column an analyst may change

-- The signed-in person's district, as an uncorrelated subquery so Postgres runs it once per statement. RLS on
-- analysts lets each person read only their own row, so anyone who is not an analyst gets null, and null matches
-- no ticket.
create policy "districts: analysts read the list" on public.districts
  for select to authenticated using (true);

create policy "analysts: read your own row" on public.analysts
  for select to authenticated using (user_id = (select auth.uid()));

create policy "tickets: read your district" on public.tickets
  for select to authenticated
  using (district_id = (select a.district_id from public.analysts a where a.user_id = (select auth.uid())));

create policy "tickets: change status in your district" on public.tickets
  for update to authenticated
  using (district_id = (select a.district_id from public.analysts a where a.user_id = (select auth.uid())))
  with check (district_id = (select a.district_id from public.analysts a where a.user_id = (select auth.uid())));

-- A sighting or an event is visible when its ticket is: the subquery on tickets runs under the tickets policies.
create policy "sightings: read those of tickets you can read" on public.sightings
  for select to authenticated
  using (exists (select 1 from public.tickets t where t.id = sightings.ticket_id));

create policy "ticket events: read those of tickets you can read" on public.ticket_events
  for select to authenticated
  using (exists (select 1 from public.tickets t where t.id = ticket_events.ticket_id));
