"""State management: fly.toml discovery, deployment.json, SECRETS.json."""

import json
import re
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


# -- primary_region ---------------------------------------------------------

def read_primary_region(fly_toml):
    """Read primary_region from fly.toml. Returns the region string or None."""
    for line in Path(fly_toml).read_text().splitlines():
        if line.strip().startswith("primary_region"):
            val = line.split("=", 1)[1].strip().strip("'\"")
            return val or None
    return None


def write_primary_region(fly_toml, region):
    """Write primary_region into fly.toml.

    Replaces an existing primary_region line, or inserts one after the
    app = line if none exists.
    """
    path = Path(fly_toml)
    text = path.read_text()
    if re.search(r"^primary_region\s*=", text, re.MULTILINE):
        text = re.sub(
            r"^primary_region\s*=\s*.*$",
            f"primary_region = '{region}'",
            text,
            flags=re.MULTILINE,
        )
    else:
        text = re.sub(
            r"^(app\s*=\s*.*$)",
            rf"\1\nprimary_region = '{region}'",
            text,
            flags=re.MULTILINE,
        )
    path.write_text(text)


def clear_primary_region(fly_toml):
    """Remove primary_region from fly.toml so Fly prompts for it."""
    path = Path(fly_toml)
    text = path.read_text()
    text = re.sub(r"^primary_region\s*=\s*.*\n?", "", text,
                  flags=re.MULTILINE)
    path.write_text(text)


# -- [[vm]] config -----------------------------------------------------------

def read_vm_config(fly_toml):
    """Read the [[vm]] section from fly.toml.

    Returns a dict (e.g. {"memory": "256mb", "cpu_kind": "shared",
    "cpus": "1"}) or None if no [[vm]] section exists.
    """
    lines = Path(fly_toml).read_text().splitlines()
    in_vm = False
    config = {}
    for line in lines:
        stripped = line.strip()
        if stripped == "[[vm]]":
            in_vm = True
            continue
        if in_vm:
            if stripped.startswith("[") or stripped.startswith("[["):
                break
            if "=" in stripped:
                key, val = stripped.split("=", 1)
                config[key.strip()] = val.strip().strip("'\"")
    return config or None


def write_vm_config(fly_toml, config):
    """Write a [[vm]] section into fly.toml.

    Clears any existing [[vm]] section first, then appends the new one.
    config is a dict, e.g. {"memory": "256mb", "cpu_kind": "shared",
    "cpus": "1"}.
    """
    clear_vm_config(fly_toml)
    path = Path(fly_toml)
    text = path.read_text().rstrip("\n")
    text += "\n\n[[vm]]\n"
    for key, val in config.items():
        text += f"  {key} = '{val}'\n"
    path.write_text(text)


def clear_vm_config(fly_toml):
    """Remove the [[vm]] section from fly.toml so Fly prompts for VM size.

    Returns a dict of the removed config, or None if no [[vm]] existed.
    """
    path = Path(fly_toml)
    lines = path.read_text().splitlines()
    config = {}
    result = []
    in_vm = False
    for line in lines:
        stripped = line.strip()
        if stripped == "[[vm]]":
            in_vm = True
            continue
        if in_vm:
            if stripped.startswith("[") or stripped.startswith("[["):
                in_vm = False
                result.append(line)
            elif "=" in stripped:
                key, val = stripped.split("=", 1)
                config[key.strip()] = val.strip().strip("'\"")
        else:
            result.append(line)
    while result and result[-1].strip() == "":
        result.pop()
    path.write_text("\n".join(result) + "\n")
    return config or None


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
