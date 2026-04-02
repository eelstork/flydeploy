"""State management: fly.toml discovery, deployment.json, SECRETS.json."""

import json
from datetime import datetime
from pathlib import Path

# Directories to skip when searching for fly.toml
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
              ".tox", "setup-history", ".fly"}


def find_fly_toml(start_dir):
    """Find fly.toml under start_dir. Returns Path or None.

    Raises ValueError if multiple fly.toml files are found.
    """
    start = Path(start_dir)
    found = []
    for path in start.rglob("fly.toml"):
        if not any(skip in path.parts for skip in _SKIP_DIRS):
            found.append(path)
    if len(found) == 1:
        return found[0]
    if len(found) > 1:
        listing = "\n  ".join(str(p) for p in found)
        raise ValueError(
            f"Multiple fly.toml files found:\n  {listing}\n"
            "Specify the path explicitly."
        )
    return None


def read_app_name(fly_toml):
    """Read the app name from a fly.toml file."""
    for line in Path(fly_toml).read_text().splitlines():
        if line.startswith("app"):
            return line.split("=", 1)[1].strip().strip("'\"")
    return None


def write_app_name(fly_toml, name, placeholder=None):
    """Write app name into fly.toml.

    If placeholder is given, replaces the first occurrence of it.
    Otherwise replaces the existing app = "..." line.
    """
    path = Path(fly_toml)
    content = path.read_text()
    if placeholder and placeholder in content:
        path.write_text(content.replace(placeholder, name, 1))
    else:
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("app"):
                lines[i] = f'app = "{name}"'
                break
        path.write_text("\n".join(lines) + "\n")


def reset_fly_toml(fly_toml, app_name, placeholder):
    """Reset fly.toml app name back to the placeholder."""
    path = Path(fly_toml)
    if not path.exists():
        return
    content = path.read_text()
    if app_name in content and app_name != placeholder:
        path.write_text(content.replace(app_name, placeholder, 1))


# -- deployment.json --------------------------------------------------------

def load_deployment(path):
    """Read deployment.json. Returns dict (empty if file doesn't exist)."""
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_deployment(path, **updates):
    """Merge updates into deployment.json, overwriting matched keys.

    Automatically sets deployed_at to the current timestamp.
    """
    path = Path(path)
    state = load_deployment(path)
    state.update(updates)
    state["deployed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


# -- SECRETS.json -----------------------------------------------------------

def load_secrets(path):
    """Read SECRETS.json. Returns dict (empty if file doesn't exist)."""
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_secrets(path, updates):
    """Merge updates into SECRETS.json, skipping keys that already exist."""
    path = Path(path)
    data = load_secrets(path)
    for k, v in updates.items():
        if k not in data:
            data[k] = v
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def update_secret(path, key, value):
    """Update (or insert) a single key in SECRETS.json, overwriting."""
    path = Path(path)
    data = load_secrets(path)
    data[key] = value
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
