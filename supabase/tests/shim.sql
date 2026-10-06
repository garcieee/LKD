-- A local stand-in for what a Supabase project already has and the migration relies on: the three API roles, the
-- auth schema with auth.users and auth.uid(), and Supabase's default grants on public (everything to anon and
-- authenticated, which the migration has to take back). Used only by run_local.sh, never on a real project.
create role anon nologin noinherit;
create role authenticated nologin noinherit;
create role service_role nologin noinherit bypassrls;

create schema auth;
create table auth.users (id uuid primary key, email text);
-- Same contract as Supabase's auth.uid(): the sub claim of the request's JWT, or null.
create function auth.uid() returns uuid language sql stable as $$
  select (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid
$$;

grant usage on schema auth to anon, authenticated, service_role;
grant usage on schema public to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;
alter default privileges in schema public grant all on functions to anon, authenticated, service_role;
