# Supabase: analyst sign-in and district roles

Supabase does two jobs for Lakad: it signs analysts in (Auth), and it holds which district each analyst may see. The tickets stay on the Lakad server in SQLite (`db/lakad.db`), never in Supabase, and so do photos and videos.

| Table | Holds |
|---|---|
| `districts` | 1 District 1 (Western Makati), 2 District 2 (Eastern Makati) |
| `analysts` | One row per analyst: `user_id`, `name`, and either `district_id` (1 or 2) or `citywide = true` (both districts, plus tickets that fall in neither). Never both, never neither |

Row level security: a signed-in person reads only their own `analysts` row and the district names. Only an admin (the SQL editor) writes either table, so nobody can give themselves a role. The publishable key alone reads nothing. The Lakad server checks every dashboard request against the caller's row.

## Set up a project

1. Create a project on [supabase.com](https://supabase.com), free tier. Region: Southeast Asia (Singapore), the closest to Manila.
2. **SQL Editor:** paste `supabase/migrations/20261007010000_district_roles.sql` and run it.
3. **Authentication > Sign In / Providers:** turn off "Allow new users to sign up" (an admin creates every analyst account). Keep anonymous sign-ins off.
4. **Authentication > Users > Add user > Create new user:** the analyst's email and a password. Tick "Auto Confirm User" so they can sign in at once.
5. **SQL Editor:** give each analyst a role.

   ```sql
   insert into public.analysts (user_id, district_id, name)
   select id, 1, 'District 1 analyst' from auth.users where email = 'district1@example.com';

   insert into public.analysts (user_id, district_id, name)
   select id, 2, 'District 2 analyst' from auth.users where email = 'district2@example.com';

   insert into public.analysts (user_id, citywide, name)
   select id, true, 'Citywide analyst' from auth.users where email = 'citywide@example.com';
   ```

   To remove access, delete the row. The account can still sign in, but the dashboard says it has no district and the server refuses it (within 60 s, the server's cache).

   ```sql
   delete from public.analysts where user_id = (select id from auth.users where email = 'district1@example.com');
   ```

6. **Keys:** the project URL and the **publishable** key (`sb_publishable_…`) are under Project Settings > Data API and Project Settings > API Keys, or behind the project's Connect button. They go in two git-ignored files:

   | File | Variables |
   |---|---|
   | `dashboard/.env.local` | `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY` |
   | `server/.env` | `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` (the server uses them to check each sign-in) |

   The secret key (`sb_secret_…`) is not used anywhere in Lakad: never copy it into a file or into chat. Restart the dashboard and the server after setting the variables. Leave them empty and Lakad runs without sign-in, as before.
7. **Advisors > Security Advisor:** run it after the migration. Expect no warnings.

## Test the rules

`bash supabase/tests/run_local.sh` applies the migrations to a throwaway local Postgres and runs the RLS tests in `tests/rls_test.sql`. It needs `initdb`, `pg_ctl` and `psql` (`brew install postgresql`) and leaves nothing behind.

## Good to know

- A free project pauses after a week without use. Open it in the Supabase dashboard to wake it before a demo.
- The dashboard keeps the analyst's session in the browser's local storage and refreshes it before it expires (supabase-js defaults). Sign out on shared computers.
