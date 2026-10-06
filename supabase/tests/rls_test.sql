-- Row level security tests for the district roles: what each kind of caller can and cannot do. Run by run_local.sh
-- after shim.sql and every migration. Each block acts as one caller (tests.login) and raises "FAILED: ..." on the
-- first broken promise.
set client_min_messages = warning;

create schema tests;
grant usage on schema tests to anon, authenticated, service_role;

-- Act as a signed-in user, the way PostgREST does: the JWT claims in a setting, then the role.
create function tests.login(uid uuid) returns void language plpgsql as $$
begin
  perform set_config('request.jwt.claims', json_build_object('sub', uid, 'role', 'authenticated')::text, true);
  perform set_config('role', 'authenticated', true);
end $$;

-- Act as the publishable key with no user (anon).
create function tests.login_anon() returns void language plpgsql as $$
begin
  perform set_config('request.jwt.claims', json_build_object('role', 'anon')::text, true);
  perform set_config('role', 'anon', true);
end $$;

create function tests.check(ok boolean, what text) returns void language plpgsql as $$
begin
  if ok is not true then
    raise exception 'FAILED: %', what;
  end if;
end $$;
grant execute on all functions in schema tests to anon, authenticated, service_role;

-- Fixtures: one analyst per role, and a signed-in person who is no analyst.
insert into auth.users (id, email) values
  ('11111111-1111-4111-8111-111111111111', 'district1@example.com'),
  ('22222222-2222-4222-8222-222222222222', 'district2@example.com'),
  ('cccccccc-cccc-4ccc-8ccc-cccccccccccc', 'citywide@example.com'),
  ('33333333-3333-4333-8333-333333333333', 'nobody@example.com');
insert into public.analysts (user_id, district_id, citywide, name) values
  ('11111111-1111-4111-8111-111111111111', 1, false, 'District 1 analyst'),
  ('22222222-2222-4222-8222-222222222222', 2, false, 'District 2 analyst'),
  ('cccccccc-cccc-4ccc-8ccc-cccccccccccc', null, true, 'Citywide analyst');

-- 1. Each analyst reads exactly their own row, which is what the Lakad server asks for with their token.
do $$ declare got text; begin
  perform tests.login('11111111-1111-4111-8111-111111111111');
  select string_agg(coalesce(district_id::text, '-') || ':' || citywide, ',') into got from public.analysts;
  perform tests.check(got = '1:false', 'the District 1 analyst reads their own row only, got ' || coalesce(got, 'nothing'));

  perform tests.login('22222222-2222-4222-8222-222222222222');
  select string_agg(coalesce(district_id::text, '-') || ':' || citywide, ',') into got from public.analysts;
  perform tests.check(got = '2:false', 'the District 2 analyst reads their own row only, got ' || coalesce(got, 'nothing'));

  perform tests.login('cccccccc-cccc-4ccc-8ccc-cccccccccccc');
  select string_agg(coalesce(district_id::text, '-') || ':' || citywide, ',') into got from public.analysts;
  perform tests.check(got = '-:true', 'the citywide analyst reads their own row only, got ' || coalesce(got, 'nothing'));
end $$;

-- 2. Signed in without a row: no role, so the Lakad server refuses them.
do $$ declare n int; begin
  perform tests.login('33333333-3333-4333-8333-333333333333');
  select count(*) into n from public.analysts;
  perform tests.check(n = 0, 'a signed-in non-analyst reads no analyst row, read ' || n);
end $$;

-- 3. Any signed-in user may read the two district names (for labels); nothing else is shared.
do $$ declare n int; begin
  perform tests.login('33333333-3333-4333-8333-333333333333');
  select count(*) into n from public.districts;
  perform tests.check(n = 2, 'the district list has 2 rows, got ' || n);
end $$;

-- 4. The publishable key alone (anon) cannot read either table.
do $$ declare t text; begin
  perform tests.login_anon();
  foreach t in array array['districts', 'analysts'] loop
    begin
      execute format('select count(*) from public.%I', t);
      raise exception 'FAILED: anon read public.%', t;
    exception when insufficient_privilege then null;
    end;
  end loop;
end $$;

-- 5. Nobody can give themselves a role, change their own, widen it to citywide, or touch the district list.
do $$ declare stmt text; begin
  perform tests.login('11111111-1111-4111-8111-111111111111');
  foreach stmt in array array[
    'update public.analysts set district_id = 2 where user_id = ''11111111-1111-4111-8111-111111111111''',
    'update public.analysts set citywide = true, district_id = null where user_id = ''11111111-1111-4111-8111-111111111111''',
    'delete from public.analysts where user_id = ''22222222-2222-4222-8222-222222222222''',
    'insert into public.analysts (user_id, citywide) values (''33333333-3333-4333-8333-333333333333'', true)',
    'insert into public.districts (id, name) values (3, ''District 3'')',
    'update public.districts set name = ''x'' where id = 1'
  ] loop
    begin
      execute stmt;
      raise exception 'FAILED: an analyst ran %', stmt;
    exception when insufficient_privilege then null;
    end;
  end loop;

  perform tests.login('33333333-3333-4333-8333-333333333333');
  begin
    insert into public.analysts (user_id, district_id) values ('33333333-3333-4333-8333-333333333333', 1);
    raise exception 'FAILED: a non-analyst gave themselves District 1';
  exception when insufficient_privilege then null;
  end;
end $$;

-- 6. A role is one district or the whole city: never both, never neither (even an admin cannot store that).
do $$ begin
  begin
    insert into public.analysts (user_id, district_id, citywide) values ('33333333-3333-4333-8333-333333333333', 1, true);
    raise exception 'FAILED: a row with a district and citywide was accepted';
  exception when check_violation then null;
  end;
  begin
    insert into public.analysts (user_id, district_id, citywide) values ('33333333-3333-4333-8333-333333333333', null, false);
    raise exception 'FAILED: a row with neither a district nor citywide was accepted';
  exception when check_violation then null;
  end;
end $$;

-- 7. Deleting an analyst's row takes the role away on their next request.
delete from public.analysts where user_id = '22222222-2222-4222-8222-222222222222';
do $$ declare n int; begin
  perform tests.login('22222222-2222-4222-8222-222222222222');
  select count(*) into n from public.analysts;
  perform tests.check(n = 0, 'a removed analyst has no role left, read ' || n);
end $$;

-- 8. Guards for every future migration: every table in public has RLS on, anon holds no privilege on any of them,
-- and authenticated holds nothing but select.
do $$ declare bad text; begin
  select string_agg(c.relname, ', ') into bad
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public' and c.relkind in ('r', 'p') and not c.relrowsecurity;
  perform tests.check(bad is null, 'tables in public without RLS: ' || coalesce(bad, ''));

  select string_agg(grantee || ' ' || privilege_type || ' on ' || table_name, ', ') into bad
  from information_schema.role_table_grants
  where table_schema = 'public' and (grantee = 'anon' or (grantee = 'authenticated' and privilege_type <> 'SELECT'));
  perform tests.check(bad is null, 'grants that should not exist: ' || coalesce(bad, ''));
end $$;
