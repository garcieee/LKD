-- Row level security tests: what each kind of caller can and cannot do. Run by run_local.sh after shim.sql and
-- every migration. Each block acts as one caller (tests.login) and raises "FAILED: ..." on the first broken promise.
set client_min_messages = warning;

create schema tests;
grant usage on schema tests to anon, authenticated, service_role;

-- Act as a signed-in user, the way PostgREST does: the JWT claims in a setting, then the role.
create function tests.login(uid uuid) returns void language plpgsql as $$
begin
  perform set_config('request.jwt.claims', json_build_object('sub', uid, 'role', 'authenticated')::text, true);
  perform set_config('role', 'authenticated', true);
end $$;

-- Act as a key with no user: 'anon' (publishable key) or 'service_role' (secret key).
create function tests.login_as(role_name text) returns void language plpgsql as $$
begin
  perform set_config('request.jwt.claims', json_build_object('role', role_name)::text, true);
  perform set_config('role', role_name, true);
end $$;

create function tests.check(ok boolean, what text) returns void language plpgsql as $$
begin
  if ok is not true then
    raise exception 'FAILED: %', what;
  end if;
end $$;
grant execute on all functions in schema tests to anon, authenticated, service_role;

-- Fixtures: an analyst per district, a signed-in person who is no analyst, and four tickets.
insert into auth.users (id, email) values
  ('11111111-1111-4111-8111-111111111111', 'district1@example.com'),
  ('22222222-2222-4222-8222-222222222222', 'district2@example.com'),
  ('33333333-3333-4333-8333-333333333333', 'nobody@example.com');
insert into public.analysts (user_id, district_id, name) values
  ('11111111-1111-4111-8111-111111111111', 1, 'District 1 analyst'),
  ('22222222-2222-4222-8222-222222222222', 2, 'District 2 analyst');
insert into public.tickets (id, category, district_id, lat, lng) values
  ('t-d1', 'pothole', 1, 14.5547, 121.0244),         -- Ayala
  ('t-d1-sos', 'sos', 1, 14.5650, 121.0300),
  ('t-d2', 'flooded_drain', 2, 14.5670, 121.0450),   -- Guadalupe
  ('t-none', 'pothole', null, 14.5450, 121.0550);    -- an EMBO barangay, now Taguig: no district
insert into public.sightings (id, ticket_id, lat, lng) values
  ('s-d1', 't-d1', 14.5547, 121.0244),
  ('s-d2', 't-d2', 14.5670, 121.0450);

-- 1. A District 1 analyst sees District 1's tickets, the SOS among them, and their sightings. Nothing else.
do $$ declare ids text; begin
  perform tests.login('11111111-1111-4111-8111-111111111111');
  select string_agg(id, ',' order by id) into ids from public.tickets;
  perform tests.check(ids = 't-d1,t-d1-sos', 'District 1 sees t-d1,t-d1-sos, got ' || coalesce(ids, 'nothing'));
  select string_agg(id, ',' order by id) into ids from public.sightings;
  perform tests.check(ids = 's-d1', 'District 1 sees sighting s-d1 only, got ' || coalesce(ids, 'nothing'));
end $$;

-- 2. A District 2 analyst sees District 2 only.
do $$ declare ids text; begin
  perform tests.login('22222222-2222-4222-8222-222222222222');
  select string_agg(id, ',' order by id) into ids from public.tickets;
  perform tests.check(ids = 't-d2', 'District 2 sees t-d2, got ' || coalesce(ids, 'nothing'));
  select string_agg(id, ',' order by id) into ids from public.sightings;
  perform tests.check(ids = 's-d2', 'District 2 sees sighting s-d2 only, got ' || coalesce(ids, 'nothing'));
end $$;

-- 3. Signed in but not an analyst: nothing at all.
do $$ declare n int; begin
  perform tests.login('33333333-3333-4333-8333-333333333333');
  select count(*) into n from public.tickets;
  perform tests.check(n = 0, 'a non-analyst sees no ticket, saw ' || n);
  select count(*) into n from public.sightings;
  perform tests.check(n = 0, 'a non-analyst sees no sighting, saw ' || n);
  select count(*) into n from public.analysts;
  perform tests.check(n = 0, 'a non-analyst sees no analyst row, saw ' || n);
end $$;

-- 4. The publishable key alone (anon) cannot read or write a single table.
do $$ declare t text; begin
  perform tests.login_as('anon');
  foreach t in array array['districts', 'analysts', 'tickets', 'sightings', 'ticket_events'] loop
    begin
      execute format('select count(*) from public.%I', t);
      raise exception 'FAILED: anon read public.%', t;
    exception when insufficient_privilege then null;
    end;
  end loop;
end $$;

-- 5. An analyst reads their own analyst row only, so cannot list who covers which district.
do $$ declare ids text; begin
  perform tests.login('11111111-1111-4111-8111-111111111111');
  select string_agg(name, ',') into ids from public.analysts;
  perform tests.check(ids = 'District 1 analyst', 'an analyst sees only their own row, got ' || coalesce(ids, 'nothing'));
end $$;

-- 6. An analyst changes the status of a ticket in their district. The change is stamped and logged with their id.
do $$ declare n int; fixed timestamptz; e record; begin
  perform tests.login('11111111-1111-4111-8111-111111111111');
  update public.tickets set status = 'fixed' where id = 't-d1';
  get diagnostics n = row_count;
  perform tests.check(n = 1, 'District 1 changes t-d1, changed ' || n || ' rows');
  select fixed_at into fixed from public.tickets where id = 't-d1';
  perform tests.check(fixed is not null, 'fixing a ticket stamps fixed_at');
  select actor, from_status, to_status into e from public.ticket_events where ticket_id = 't-d1';
  perform tests.check(e.actor = '11111111-1111-4111-8111-111111111111' and e.from_status = 'open' and e.to_status = 'fixed',
    'the change is logged with who made it, got ' || coalesce(row_to_json(e)::text, 'no event'));
end $$;

-- 7. An analyst cannot change a ticket in the other district, or one with no district: the update matches nothing.
do $$ declare n int; begin
  perform tests.login('11111111-1111-4111-8111-111111111111');
  update public.tickets set status = 'verified' where id in ('t-d2', 't-none');
  get diagnostics n = row_count;
  perform tests.check(n = 0, 'District 1 changes nothing outside District 1, changed ' || n || ' rows');
end $$;
do $$ begin
  perform tests.check((select status from public.tickets where id = 't-d2') = 'open', 't-d2 is untouched');
end $$;

-- 8. The status is the only column an analyst may change: not the district, not the priority.
do $$ declare col text; begin
  perform tests.login('11111111-1111-4111-8111-111111111111');
  foreach col in array array['district_id = 2', 'priority = 100', 'category = ''other''', 'fixed_at = null'] loop
    begin
      execute 'update public.tickets set ' || col || ' where id = ''t-d1''';
      raise exception 'FAILED: an analyst ran update ... set %', col;
    exception when insufficient_privilege then null;
    end;
  end loop;
end $$;

-- 9. No inserts or deletes for an analyst, and above all no way to pick their own district.
do $$ declare stmt text; begin
  perform tests.login('11111111-1111-4111-8111-111111111111');
  foreach stmt in array array[
    'insert into public.tickets (id, category, district_id, lat, lng) values (''x'', ''pothole'', 1, 14.55, 121.02)',
    'delete from public.tickets where id = ''t-d1''',
    'insert into public.sightings (id, ticket_id, lat, lng) values (''x'', ''t-d1'', 14.55, 121.02)',
    'insert into public.ticket_events (ticket_id, to_status) values (''t-d1'', ''open'')',
    'delete from public.ticket_events',
    'update public.analysts set district_id = 2 where user_id = ''11111111-1111-4111-8111-111111111111''',
    'insert into public.analysts (user_id, district_id) values (''33333333-3333-4333-8333-333333333333'', 1)',
    'insert into public.districts (id, name) values (3, ''District 3'')'
  ] loop
    begin
      execute stmt;
      raise exception 'FAILED: an analyst ran %', stmt;
    exception when insufficient_privilege then null;
    end;
  end loop;
end $$;

-- 10. A status outside the five is refused.
do $$ begin
  perform tests.login('11111111-1111-4111-8111-111111111111');
  begin
    update public.tickets set status = 'done' where id = 't-d1-sos';
    raise exception 'FAILED: status "done" was accepted';
  exception when check_violation then null;
  end;
end $$;

-- 11. The server (secret key) sees every ticket, the unrouted one too, and writes tickets and sightings.
-- A status change it makes is logged with no actor.
do $$ declare n int; e record; begin
  perform tests.login_as('service_role');
  select count(*) into n from public.tickets;
  perform tests.check(n = 4, 'the server sees all 4 tickets, saw ' || n);
  insert into public.tickets (id, category, district_id, lat, lng) values ('t-new', 'pothole', 2, 14.567, 121.045);
  insert into public.sightings (id, ticket_id, lat, lng) values ('s-new', 't-new', 14.567, 121.045);
  update public.tickets set status = 'open' where id = 't-d1';  -- a new report reopens the fixed ticket
  select actor, from_status, to_status into e from public.ticket_events where ticket_id = 't-d1' order by id desc limit 1;
  perform tests.check(e.actor is null and e.from_status = 'fixed' and e.to_status = 'open',
    'a server change is logged with no actor, got ' || coalesce(row_to_json(e)::text, 'no event'));
  perform tests.check((select fixed_at from public.tickets where id = 't-d1') is null, 'reopening clears fixed_at');
end $$;

-- 12. Deleting an analyst row takes access away at once.
delete from public.analysts where user_id = '22222222-2222-4222-8222-222222222222';
do $$ declare n int; begin
  perform tests.login('22222222-2222-4222-8222-222222222222');
  select count(*) into n from public.tickets;
  perform tests.check(n = 0, 'a removed analyst sees nothing, saw ' || n);
end $$;

-- 13. Guards for every future migration: every table in public has RLS on, anon holds no privilege on any of them,
-- authenticated holds nothing but select, and the private schema is out of reach of both.
do $$ declare bad text; begin
  select string_agg(c.relname, ', ') into bad
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public' and c.relkind in ('r', 'p') and not c.relrowsecurity;
  perform tests.check(bad is null, 'tables in public without RLS: ' || coalesce(bad, ''));

  select string_agg(grantee || ' ' || privilege_type || ' on ' || table_name, ', ') into bad
  from information_schema.role_table_grants
  where table_schema = 'public' and (grantee = 'anon' or (grantee = 'authenticated' and privilege_type <> 'SELECT'));
  perform tests.check(bad is null, 'grants that should not exist: ' || coalesce(bad, ''));

  perform tests.check(not has_schema_privilege('anon', 'private', 'usage')
    and not has_schema_privilege('authenticated', 'private', 'usage'), 'the private schema is not reachable from the API');
end $$;
