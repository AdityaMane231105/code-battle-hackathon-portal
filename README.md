# Code Battle — Online Hackathon Portal

Code Battle is a server-rendered Django application for a four-stage programming competition. It includes participant accounts and profiles, qualification-gated timed rounds, automatic multiple-choice scoring, manual code review, a scored leaderboard, and a protected staff console.

## Architecture

- **Django 5.2/6.x** provides authentication, CSRF protection, server-side forms, the ORM, and the staff admin. Python is the only application runtime; Node.js is not required.
- **SQLite** persists users, profiles, rounds, challenges, attempts, scores, and review audit fields. The schema is defined in Django models and versioned with migrations.
- **Django templates + responsive CSS/vanilla JavaScript** render the public site, participant area, timed attempts, and staff views.
- **Waitress + WhiteNoise** provide a cross-platform WSGI server and static-file serving for a single-instance deployment.

## Prerequisites

- Python 3.12 or newer (Python 3.14 is supported by the current Django release).
- `pip`.

## Local setup

From the project root in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Open <http://127.0.0.1:8000/>. Django reads environment variables from the process; `.env` is an example/reference file and is not auto-loaded. For local development, the settings defaults work without a `.env` file.

### Optional demo accounts

The seed command creates rounds and challenges without creating accounts. To also create a demo administrator and sample participant accounts, set passwords in the current PowerShell process (do not commit them) and run:

```powershell
$env:DEMO_ADMIN_PASSWORD = "use-a-unique-local-password"
$env:DEMO_PARTICIPANT_PASSWORD = "use-a-different-local-password"
python manage.py seed_demo --with-users
Remove-Item Env:DEMO_ADMIN_PASSWORD
Remove-Item Env:DEMO_PARTICIPANT_PASSWORD
```

Demo usernames are `admin@codebattle.local`, `alex@demo.codebattle.local`, and `sam@demo.codebattle.local`. The sample participants are explicitly labelled in the leaderboard. Seeded scores are illustrative only and the site displays a demo banner. For a real event, create a fresh database, seed the competition, create actual accounts, and turn off **Demo data** under Django admin → Competition settings. The seed command is safe to rerun for the provided sample rounds; it deliberately marks the competition data as demo.

Create a separate administrator in a non-demo setup with:

```powershell
python manage.py createsuperuser
```

Django superusers can access both `/django-admin/` and the staff console at `/staff/`.

## Running tests and checks

```powershell
python manage.py test
python manage.py check
python manage.py makemigrations --check --dry-run
```

The automated tests cover account registration, scoring, qualification rules, round scheduling, private submission access, timeout closure, manual review, and staff-only operations.

## Competition operations

1. Use **Django admin → Rounds** to create/edit challenges, update schedules, set a round open or closed, configure its duration, and set its passing score. Multiple-choice answers are checked server-side; challenge ordering is unique per round.
2. Participants can start an open first round. Each later round requires a graded score at or above the previous round’s passing threshold and must itself be open.
3. Attempts are created when started, have one attempt per participant/round, and cannot be reset by refreshing. The server enforces the deadline and input limits; the browser timer is only a convenience.
4. Objective questions are automatically scored. Coding and debugging responses are stored without execution and placed in the staff review queue. Staff record a manual score and feedback; automatic points are preserved if a round mixes challenge types.
5. The leaderboard shows only graded scores. Staff must close every round and clear the review queue before publishing final results.

## Configuration

Copy `.env.example` and set these variables in the process environment:

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Long, random secret; required when `DJANGO_DEBUG=False`. |
| `DJANGO_DEBUG` | Set to `False` in production. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated host names for the deployment. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Optional comma-separated HTTPS origins behind a proxy. |
| `DATABASE_PATH` | SQLite database path; defaults to `db.sqlite3` in the project root. |
| `DEMO_ADMIN_PASSWORD`, `DEMO_PARTICIPANT_PASSWORD` | Optional secrets used only by `seed_demo --with-users`. |
| `ADMIN_USERNAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` | One-time initial Render staff-account setup used by `bootstrap_admin`; an existing account is never reset by the command. |

The application enables secure session/CSRF cookies, HTTPS redirects, HSTS, clickjacking protection, and content-type protection when `DJANGO_DEBUG=False`. The TLS-terminating host must forward HTTPS correctly. Keep the SQLite database on a persistent disk and back it up.

## Deploy to Render

The included `render.yaml` configures a **Free** web service, runs migrations and sample-data seeding, bootstraps the initial admin from Render environment variables, and serves static files. This free deployment uses SQLite on Render's ephemeral filesystem: participant accounts, submissions, scores, and event changes can be lost when the instance restarts, sleeps, or deploys. Treat it as a demo only; do not use it for a real competition. For durable event data, change the service to a paid plan and attach persistent storage, or migrate to managed PostgreSQL. The deployment seed uses `--if-empty` to avoid overwriting event settings while the current instance filesystem remains intact.

1. Push this project to a GitHub repository you control.
2. In Render, choose **New → Blueprint**, connect the repository, and apply `render.yaml`.
3. Render generates `DJANGO_SECRET_KEY` and `ADMIN_PASSWORD`; enter an `ADMIN_EMAIL` when prompted. The first deploy seeds the sample rounds and creates the `organizer` staff account. Find the generated admin password in that service’s environment settings; change it after the first sign-in.
4. Wait for `/health/` to pass, open the `onrender.com` URL, and sign in at `/accounts/login/` with username `organizer` and the generated `ADMIN_PASSWORD`. Change it after the first sign-in. Open `/staff/` for event operations and `/django-admin/` to manage rounds and challenges.
5. The free instance may sleep when idle, and local files are ephemeral. For a real event, upgrade to durable storage before collecting participant data. Review the seeded challenge prompts, change round schedules/statuses, disable the demo banner in Competition settings, and replace the generated bootstrap admin password. The seeded sample rounds are explicitly demo data.

The service hostname is accepted automatically from Render’s `RENDER_EXTERNAL_HOSTNAME`. If you add a custom domain, add its host to `DJANGO_ALLOWED_HOSTS` and its `https://` origin to `DJANGO_CSRF_TRUSTED_ORIGINS`.

## Other deployment

This MVP is designed for a single application instance with a persistent local volume. Install dependencies, configure the environment above, then:

```powershell
python manage.py migrate
python manage.py collectstatic --noinput
waitress-serve --listen=0.0.0.0:8000 codebattle.wsgi:application
```

Use the equivalent shell syntax for Linux-based hosting. Point the platform’s persistent disk at `DATABASE_PATH`, configure TLS at the edge, set the health check to `/`, and never run with `DJANGO_DEBUG=True` on a public deployment. A production multi-instance deployment should replace SQLite with PostgreSQL and provision backups, monitoring, and a managed secret store.

## Known limitations and safety boundaries

- **Untrusted code is not run.** Coding/debugging answers are safely stored as text and require staff review. Automatic execution needs a separately deployed, isolated runner with resource limits and an authenticated job API; no such service is bundled or claimed here.
- The leaderboard refreshes when its page is loaded; this implementation does not provide push/real-time updates.
- SQLite is suitable for local use and small single-instance events, not multi-host write scaling.
- Email verification, password reset email delivery, anti-abuse controls, and third-party identity providers need mail/service configuration and are not enabled.
- The browser countdown is not authoritative. The application checks elapsed time on the server; automatic closure occurs when an expired attempt is revisited or submitted.
- Admin audit metadata records submission and grading timestamps and the grading account. It is not an immutable, tamper-evident audit log.
- Demo participant scores are sample records, not real event results.
