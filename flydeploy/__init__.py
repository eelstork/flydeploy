"""Fly.io deployment toolkit — shared functions for deploy/destroy scripts."""

from .core import open_log, close_log, run, prompt, ask_mode
from .state import (
    find_fly_toml, read_app_name, write_app_name, reset_fly_toml,
    load_deployment, save_deployment,
    load_secrets, save_secrets, update_secret,
)
from .steps import (
    SecretDef, HandlerContext,
    preflight, create_app, setup_postgres,
    configure_secrets, deploy, smoke_test,
    confirm_destroy, destroy_app, destroy_postgres,
)

__all__ = [
    "ask_mode", "open_log", "close_log", "run", "prompt",
    "find_fly_toml", "read_app_name", "write_app_name", "reset_fly_toml",
    "load_deployment", "save_deployment",
    "load_secrets", "save_secrets", "update_secret",
    "SecretDef", "HandlerContext",
    "preflight", "create_app", "setup_postgres",
    "configure_secrets", "deploy", "smoke_test",
    "confirm_destroy", "destroy_app", "destroy_postgres",
]
