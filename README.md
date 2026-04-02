# launcher

Shared tools for project deployment. Currently provides the `flydeploy`
package for Fly.io deployments.

## flydeploy

A Python toolkit that extracts the common deploy/destroy patterns into
reusable functions. Each project's `deploy.py` and `destroy.py` remain
short, project-specific scripts that call library functions.

### Install

```bash
pip install -e path/to/launcher
```

Or from git:

```bash
pip install git+https://github.com/eelstork/launcher.git
```

### Example deploy.py

```python
#!/usr/bin/env python3
from pathlib import Path
from flydeploy import (
    open_log, preflight, find_fly_toml, read_app_name, write_app_name,
    create_app, setup_postgres, configure_secrets, deploy, smoke_test,
    save_deployment, SecretDef,
)

ROOT = Path(__file__).parent
SECRETS_PATH = ROOT / "SECRETS.json"
DEPLOYMENT_PATH = ROOT / "deployment.json"
PLACEHOLDER = "my-app-placeholder"

SECRETS = {
    "EDENAI_API_KEY": SecretDef("EdenAI API key (app.edenai.run)"),
    "OPENAI_API_KEY": SecretDef(
        "OpenAI API key",
        optional=True,
        group="api_key",
    ),
}

if __name__ == "__main__":
    open_log(ROOT / "setup_log.txt", history_dir=ROOT / "setup-history")

    fast = input("\nFast deploy? [Y/n]: ").strip().lower() in ("", "y", "yes")

    print("\n[1] Preflight")
    user = preflight()
    print(f"      Logged in as {user}")

    print("\n[2] App name")
    fly_toml = find_fly_toml(ROOT)
    app_name = read_app_name(fly_toml)
    if app_name == PLACEHOLDER:
        app_name = input("  App name: ").strip()
        write_app_name(fly_toml, app_name, placeholder=PLACEHOLDER)

    print("\n[3] Create app")
    created = create_app(app_name)
    print(f"      {'Created' if created else 'Already exists'}.")

    print("\n[4] Postgres")
    pg_name = setup_postgres(app_name, secrets_path=SECRETS_PATH)

    print("\n[5] Secrets")
    configure_secrets(app_name, SECRETS, fast=fast,
                      secrets_path=SECRETS_PATH)

    print("\n[6] Deploy")
    deploy(fly_toml=fly_toml)

    print("\n[7] Smoke test")
    smoke_test(app_name)

    save_deployment(DEPLOYMENT_PATH, app_name=app_name, pg_name=pg_name)
    print("\nDone.")
```

### Example destroy.py

```python
#!/usr/bin/env python3
from pathlib import Path
from flydeploy import (
    preflight, load_deployment, confirm_destroy,
    destroy_app, destroy_postgres, reset_fly_toml, find_fly_toml,
    read_app_name,
)

ROOT = Path(__file__).parent
DEPLOYMENT_PATH = ROOT / "deployment.json"
PLACEHOLDER = "my-app-placeholder"

if __name__ == "__main__":
    print("\nTeardown\n" + "=" * 40)

    preflight()

    state = load_deployment(DEPLOYMENT_PATH)
    app_name = state.get("app_name")
    pg_name = state.get("pg_name")

    if not app_name:
        fly_toml = find_fly_toml(ROOT)
        app_name = read_app_name(fly_toml) if fly_toml else None
    if not app_name:
        app_name = input("  App name to destroy: ").strip()

    confirm_destroy(app_name, pg_name)
    destroy_app(app_name)
    destroy_postgres(pg_name)

    fly_toml = find_fly_toml(ROOT)
    if fly_toml:
        reset_fly_toml(fly_toml, app_name, PLACEHOLDER)

    print("\nDone.\n")
```

### API at a glance

**Core** (`flydeploy.core`):
- `open_log(path, history_dir=None)` -- start logging with rotation
- `close_log()` -- close log file
- `run(cmd, *, cwd, capture, passthrough)` -- subprocess with logging
- `prompt(msg, *, required, default, secret)` -- input helper

**State** (`flydeploy.state`):
- `find_fly_toml(start_dir)` -- auto-discover fly.toml
- `read_app_name(fly_toml)` / `write_app_name(fly_toml, name, placeholder)`
- `reset_fly_toml(fly_toml, app_name, placeholder)`
- `load_deployment(path)` / `save_deployment(path, **updates)`
- `load_secrets(path)` / `save_secrets(path, updates)` / `update_secret(path, key, value)`

**Steps** (`flydeploy.steps`):
- `preflight()` -- check fly CLI + auth, returns username
- `create_app(app_name)` -- create if not exists
- `setup_postgres(app_name, pg_name, *, recover, secrets_path)` -- full postgres flow
- `configure_secrets(app_name, defs, *, fast, secrets_path)` -- declarative secrets
- `deploy(*, fly_toml, cwd)` -- fly deploy
- `smoke_test(app_name, *, path, timeout)` -- HTTP health check
- `confirm_destroy(app_name, pg_name)` -- type-name safety prompt
- `destroy_app(app_name)` / `destroy_postgres(pg_name)` -- graceful teardown

**Types**:
- `SecretDef(description, optional, group, default, suspended, handler)`
- `HandlerContext(key, on_fly, fast, secrets_path, app_name)`
