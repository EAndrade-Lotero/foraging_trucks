# Agent instructions

PsyNet is a framework for designing and deploying online psychological experiments.
The agent is there to help both with the development of the PsyNet source code,
and with the development of individual PsyNet experiments.

If the root contains a file called `experiment.py`, assume that we are working on an experiment.
Otherwise assume we are working on the PsyNet source code.

## Initial setup

- Install Python 3.13 (use same version specified in `Dockerfile`)
- Install uv (`pip3 install uv`)

## Before running commands

### System dependencies

Cloud agents will need to install the following dependencies.
Local agents should check for their availability and install if necessary.

- **Python 3.13.x**: Install a 3.13 release and verify `python3 --version`.
  Check the repository Dockerfile for the exact patch version we target
  (e.g., `psynet/resources/experiment_scripts/Dockerfile` or the root `Dockerfile`).
- **uv**: Install via `pip`.
- **PostgreSQL**: Install the server and client, ensure the service is running,
  and create the `dallinger` user/database if they do not exist. When prompted by
  `createuser -P`, set the password to `dallinger` (per the installation docs).
  Verify with `psql -h localhost -U dallinger -d dallinger`.
- **Redis**: Install the Redis server, ensure it is running, and verify with
  `redis-cli ping` (expect `PONG`).
- **Heroku CLI**: Install the CLI so `heroku` commands are available and verify
  with `heroku --version`.
- **Chromedriver**: Leave uninstalled by default; only install it if you need
  browser automation.

### Python dependencies

By default, assume a Python virtual environment located at `.venv/`.
Activate it before running Python commands.
Cloud agents should create this environment automatically via `uv`.
Local agents should prompt the user before doing so.

Install dependencies as follows:

- (For PsyNet): `uv pip install -e '.[dev,slack]'`
- (For experiments): `uv pip install -r constraints.txt`

If dependency installation fails with `pg_config executable not found`, install
PostgreSQL development headers (e.g. `libpq-dev` on Debian/Ubuntu,
`postgresql-devel` on Fedora, `brew install postgresql` on macOS) and retry.

Cursor: disable sandboxing when running PsyNet commands by setting `required_permissions: ["all"]`.

## Demos

Demos are contained in `demos/experiments` and `demos/features`.
If a user asks for the X demo, list all child directories in `demos/experiments` and `demos/features` to see which they mean.

## Running experiments locally

To run an experiment in debug mode:

```bash
cd demos/.../<experiment_name>
psynet debug local
```

For example, to run the timeline demo:

```bash
cd demos/experiments/timeline
psynet debug local
```

to see which they mean.

Wait for 8 seconds for the server to start.

Inspect the logs to see relevant URLs.
Look out for an ad page URL, something like
http://127.0.0.1:5000/ad?generate_tokens=true&recruiter=hotair.

When the demo is running, offer the user to navigate the experiment automatically.

## Navigating experiments

Cursor's browser extension can be used to interact with experiments programmatically:

1. Navigate to the ad page URL
2. Click "Begin Experiment"
3. Progress through consent and experiment pages
4. Form inputs can be filled and buttons clicked automatically

This is useful for automated testing of experiment flows.

## Database access

PsyNet uses PostgreSQL. Connect using:

```bash
psql -h localhost -U dallinger -d dallinger
```

Cursor: this needs `required_permissions: ["network"]`.

Key tables:

- `participant` - Experiment participants (id, worker_id, status, creation_time)
- `response` - Participant responses/answers
- `node` - Network nodes
- `network` - Experiment networks
- `info` - Information objects
- `experiment` - Experiment metadata
- `experiment_status` - Current experiment status

Example queries:

```sql
-- List recent participants
SELECT id, worker_id, status, creation_time FROM participant ORDER BY creation_time DESC LIMIT 5;

-- View participant responses
SELECT id, answer FROM response ORDER BY id DESC LIMIT 10;

-- List all tables
\dt
```

## Further information

If in the PsyNet repository, find further documentation in `docs`.
If in an experiment directory, find more information at https://psynetdev.gitlab.io/PsyNet/.
