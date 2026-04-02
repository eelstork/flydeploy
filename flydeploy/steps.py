"""Fly.io deployment and teardown steps."""

import json
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .core import run, prompt
from .state import load_secrets, save_secrets, update_secret


# ---------------------------------------------------------------------------
# Secret management types
# ---------------------------------------------------------------------------

@dataclass
class HandlerContext:
    """Context passed to secret handlers."""
    key: str
    on_fly: bool
    fast: bool
    secrets_path: Path
    app_name: str


@dataclass
class SecretDef:
    """Declarative definition of a Fly secret.

    description: human-readable prompt text.
    optional:    if True, user may leave blank in interactive mode.
    group:       group name for "at least one of" logic. In fast mode,
                 unconfigured alternatives are skipped when the group
                 is already covered by another key.
    default:     value to use when user leaves the prompt blank.
    suspended:   if True, the key is erased from Fly if present and
                 never set. Use for providers you've disabled.
    handler:     callable(HandlerContext) -> str | None. Takes full
                 control of prompting, local persistence, and returns
                 the value to set on Fly (or None to skip).
    """
    description: str
    optional: bool = False
    group: str | None = None
    default: str | None = None
    suspended: bool = False
    handler: Callable[[HandlerContext], str | None] | None = None


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def preflight():
    """Check that fly CLI is installed and user is authenticated.

    Returns the authenticated username.
    Calls sys.exit on failure.
    """
    if run(["fly", "version"], capture=True).returncode != 0:
        sys.exit("flyctl not found. Install from https://fly.io/docs/flyctl/install/")
    r = run(["fly", "auth", "whoami"], capture=True)
    if r.returncode != 0:
        sys.exit("Not logged in to Fly. Run: fly auth login")
    return r.stdout.strip()


# ---------------------------------------------------------------------------
# App creation
# ---------------------------------------------------------------------------

def create_app(app_name):
    """Create a Fly app if it doesn't already exist.

    Returns True if created, False if it already existed.
    """
    r = run(["fly", "apps", "list"], capture=True)
    if r.returncode != 0:
        sys.exit("Failed to list Fly apps -- check your connection.")
    if app_name in r.stdout:
        return False
    run(["fly", "apps", "create", app_name])
    return True


# ---------------------------------------------------------------------------
# Postgres
# ---------------------------------------------------------------------------

def _pg_machines_status(pg_name):
    """Return (machines_list, all_running) for a Postgres cluster."""
    r = run(["fly", "machine", "list", "--app", pg_name, "--json"],
            capture=True)
    if r.returncode != 0:
        return [], False
    try:
        machines = json.loads(r.stdout or "[]")
    except (json.JSONDecodeError, TypeError):
        return [], False
    if not machines:
        return [], False
    all_running = all(m.get("state") == "started" for m in machines)
    return machines, all_running


def _try_start_pg_machines(pg_name):
    """Attempt to start stopped Postgres machines.

    Returns True if all machines are running afterwards.
    """
    import time

    machines, already_running = _pg_machines_status(pg_name)
    if already_running:
        return True
    if not machines:
        return False

    not_running = [m for m in machines if m.get("state") != "started"]
    print(f"      {len(not_running)} Postgres machine(s) not running "
          "-- attempting to start...")
    for m in not_running:
        mid = m.get("id")
        if mid:
            run(["fly", "machine", "start", mid, "--app", pg_name],
                capture=True)
    time.sleep(5)
    _, running = _pg_machines_status(pg_name)
    return running


def _extract_pg_secrets(output):
    """Parse 'fly postgres attach' stdout.

    Returns (secrets_dict, redacted_output).
    """
    passwords = re.findall(r"^Password:\s+(\S+)", output, re.MULTILINE)
    conns = re.findall(r"^Conn:\s+(\S+)", output, re.MULTILINE)
    host_m = re.search(r"^Host:\s+(\S+)", output, re.MULTILINE)
    port_m = re.search(r"^Port:\s+(\S+)", output, re.MULTILINE)

    secrets = {}
    if host_m:
        secrets["host"] = host_m.group(1)
    if port_m:
        secrets["port"] = port_m.group(1)
    if len(conns) > 0:
        secrets["admin_conn"] = conns[0]
    if len(conns) > 1:
        secrets["app_conn"] = conns[1]

    redacted = output
    for pw in passwords:
        redacted = redacted.replace(pw, "[REDACTED]")
    return secrets, redacted


def setup_postgres(app_name, pg_name=None, *, recover=True,
                   secrets_path=None):
    """Set up and attach a Postgres cluster.

    pg_name:      cluster name (defaults to {app_name}-db).
    recover:      if True, attempt to restart stopped machines or offer
                  to recreate broken clusters.
    secrets_path: if given, Postgres credentials are saved to this
                  SECRETS.json file.

    Returns the pg_name used, or None if DATABASE_URL was already set.
    """
    # Already attached?
    r = run(["fly", "secrets", "list", "--app", app_name], capture=True)
    if "DATABASE_URL" in (r.stdout or ""):
        return None

    if pg_name is None:
        pg_name = f"{app_name}-db"

    # Does the cluster already exist?
    r = run(["fly", "postgres", "list"], capture=True)
    pg_list = r.stdout or ""

    if pg_name not in pg_list:
        print(f"      Creating Postgres cluster '{pg_name}'...")
        result = run(["fly", "postgres", "create", "--name", pg_name],
                     passthrough=True)
        if result.returncode != 0:
            sys.exit(f"Failed to create Postgres cluster '{pg_name}'.")
    elif recover:
        if not _try_start_pg_machines(pg_name):
            print(f"      Cluster '{pg_name}' exists but machines "
                  "won't start.")
            answer = input(
                "      Destroy and recreate? [y/N]: ").strip().lower()
            if answer in ("y", "yes"):
                run(["fly", "apps", "destroy", pg_name, "--yes"])
                print(f"      Creating Postgres cluster '{pg_name}'...")
                result = run(
                    ["fly", "postgres", "create", "--name", pg_name],
                    passthrough=True)
                if result.returncode != 0:
                    sys.exit("Failed to create Postgres cluster.")
            else:
                sys.exit("Cannot proceed without a running Postgres "
                         "cluster.")

    # Attach
    print(f"      Attaching '{pg_name}' to '{app_name}'...")
    result = run(["fly", "postgres", "attach", pg_name,
                  "--app", app_name], capture=True)
    raw = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        if "already attached" in raw.lower():
            pass
        else:
            print(raw)
            sys.exit(f"Failed to attach Postgres cluster '{pg_name}'.")

    # Save credentials locally
    pg_secrets, redacted = _extract_pg_secrets(result.stdout or "")
    if pg_secrets and secrets_path:
        save_secrets(secrets_path, {"postgres": pg_secrets})
        print("      Credentials saved to SECRETS.json")
    if redacted.strip():
        print(redacted)

    return pg_name


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------

def configure_secrets(app_name, defs, *, fast=True, secrets_path):
    """Configure Fly secrets from declarative definitions.

    defs:         dict of {FLY_KEY: SecretDef}.
    fast:         if True, restore from local state and skip unconfigured.
    secrets_path: path to SECRETS.json.

    Returns dict of {KEY: value} that were set on Fly.
    """
    secrets_path = Path(secrets_path)

    # What's already on Fly?
    r = run(["fly", "secrets", "list", "--app", app_name], capture=True)
    already_set = set()
    for line in (r.stdout or "").splitlines()[1:]:
        if line.strip():
            already_set.add(line.split()[0])

    local = load_secrets(secrets_path)

    # Which groups are already covered?
    covered_groups = set()
    for key, sdef in defs.items():
        if sdef.group and (key in already_set or key.lower() in local):
            covered_groups.add(sdef.group)

    # Erase suspended secrets from Fly
    for key, sdef in defs.items():
        if sdef.suspended and key in already_set:
            print(f"      {key}: suspended -- removing from Fly")
            run(["fly", "secrets", "unset", "--app", app_name, key])
            already_set.discard(key)

    to_set = {}

    for key, sdef in defs.items():
        if sdef.suspended:
            print(f"      {key}: suspended, skipping")
            continue

        # Custom handler takes full control
        if sdef.handler:
            ctx = HandlerContext(
                key=key,
                on_fly=key in already_set,
                fast=fast,
                secrets_path=secrets_path,
                app_name=app_name,
            )
            value = sdef.handler(ctx)
            if value is not None:
                to_set[key] = value
            continue

        # Already on Fly and fast mode -- skip
        if key in already_set and fast:
            print(f"      {key}: already set, skipping")
            continue

        local_key = key.lower()

        if local_key in local:
            if fast:
                value = local[local_key]
                print(f"      {key}: restoring from SECRETS.json")
            else:
                edited = input(f"  {key} [ *** ]: ").strip()
                value = edited if edited else local[local_key]
                if edited:
                    update_secret(secrets_path, local_key, edited)
        elif fast:
            if sdef.default is not None:
                value = sdef.default
                print(f"      {key}: using default: {value}")
            elif sdef.group and sdef.group in covered_groups:
                print(f"      {key}: skipping "
                      "(alternative already configured)")
                continue
            else:
                print(f"      {key}: not configured, skipping "
                      "(re-run without fast mode to set)")
                continue
        else:
            # Interactive mode
            hint = f"  {key} -- {sdef.description}"
            if key in already_set:
                hint += " (already set on Fly)"
            optional = (sdef.optional
                        or sdef.default is not None
                        or key in already_set)
            value = prompt(hint, required=not optional)
            if not value and sdef.default is not None:
                value = sdef.default
                print(f"      Using default: {value}")

        if value:
            to_set[key] = value

    if to_set:
        # Persist locally
        for k, v in to_set.items():
            update_secret(secrets_path, k.lower(), v)
        # Set on Fly
        args = ["fly", "secrets", "set", "--app", app_name]
        for k, v in to_set.items():
            args.append(f"{k}={v}")
        run(args)
        print(f"      Set {len(to_set)} secret(s).")
    else:
        print("      No new secrets to set.")

    return to_set


# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------

def deploy(*, fly_toml=None, cwd=None):
    """Run fly deploy.

    fly_toml: path to fly.toml. If given and not inside cwd, --config
              is added automatically.
    cwd:      working directory. Defaults to fly_toml's parent directory.
    """
    cmd = ["fly", "deploy"]
    if fly_toml:
        fly_toml = Path(fly_toml)
        if cwd is None:
            cwd = fly_toml.parent
        elif fly_toml.parent.resolve() != Path(cwd).resolve():
            cmd.extend(["--config", str(fly_toml)])
    result = run(cmd, cwd=cwd)
    if hasattr(result, "returncode") and result.returncode != 0:
        sys.exit("Deployment failed.")


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

def smoke_test(app_name, *, path="/", timeout=15):
    """GET the deployed app and check for a response.

    Returns True on success, False on failure.
    """
    url = f"https://{app_name}.fly.dev{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            print(f"      GET {url} -> {resp.status}")
            return resp.status < 400
    except Exception as e:
        print(f"      Could not reach {url}: {e}")
        print(f"      (app may still be starting -- check: "
              f"fly logs --app {app_name})")
        return False


# ---------------------------------------------------------------------------
# Destroy
# ---------------------------------------------------------------------------

def confirm_destroy(app_name, pg_name=None):
    """Prompt user to type the app name to confirm destruction.

    Calls sys.exit if the confirmation doesn't match.
    """
    print(f"  About to permanently destroy:")
    print(f"    App:      {app_name}  (https://{app_name}.fly.dev)")
    if pg_name:
        print(f"    Postgres: {pg_name}")
    print(f"\n  This cannot be undone.")
    answer = input(
        "\n  Type the app name to confirm, or Ctrl-C to abort: "
    ).strip()
    if answer != app_name:
        sys.exit("Confirmation did not match -- aborting.")


def destroy_app(app_name):
    """Destroy a Fly app. Skips gracefully if the app doesn't exist.

    Returns True if destroyed, False if not found.
    """
    r = run(["fly", "apps", "list"], capture=True)
    if r.returncode != 0:
        sys.exit("Failed to list Fly apps.")
    if app_name not in (r.stdout or ""):
        print(f"  App '{app_name}' not found on Fly -- skipping.")
        return False
    result = run(["fly", "apps", "destroy", app_name, "--yes"])
    if result.returncode != 0:
        print(f"  Warning: destroy returned exit code "
              f"{result.returncode}")
    return True


def destroy_postgres(pg_name):
    """Destroy a Postgres cluster. Skips gracefully if not found.

    Returns True if destroyed, False if not found or pg_name is None.
    """
    if not pg_name:
        return False
    r = run(["fly", "apps", "list"], capture=True)
    if r.returncode != 0:
        sys.exit("Failed to list Fly apps.")
    if pg_name not in (r.stdout or ""):
        print(f"  Cluster '{pg_name}' not found on Fly -- skipping.")
        return False
    result = run(["fly", "apps", "destroy", pg_name, "--yes"])
    if result.returncode != 0:
        print(f"  Warning: destroy returned exit code "
              f"{result.returncode}")
    return True
