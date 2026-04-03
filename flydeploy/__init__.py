"""Fly.io deployment toolkit — shared functions for deploy/destroy scripts."""

from .core import open_log, close_log, run, prompt, ask_mode
from .state import (
    find_fly_toml, read_app_name, write_app_name, reset_fly_toml,
    read_primary_region, write_primary_region, clear_primary_region,
    read_vm_config, write_vm_config, clear_vm_config,
    load_deployment, save_deployment,
    load_secrets, save_secrets, update_secret,
)
from .steps import (
    SecretDef, HandlerContext,
    preflight, create_app, setup_postgres,
    configure_secrets, review_fly_config, detect_region, deploy, smoke_test,
    confirm_destroy, destroy_app, destroy_postgres,
)

__all__ = [
    "ask_mode", "open_log", "close_log", "run", "prompt",
    "find_fly_toml", "read_app_name", "write_app_name", "reset_fly_toml",
    "read_primary_region", "write_primary_region", "clear_primary_region",
    "read_vm_config", "write_vm_config", "clear_vm_config",
    "load_deployment", "save_deployment",
    "load_secrets", "save_secrets", "update_secret",
    "SecretDef", "HandlerContext",
    "preflight", "create_app", "setup_postgres",
    "configure_secrets", "review_fly_config", "detect_region",
    "deploy", "smoke_test",
    "confirm_destroy", "destroy_app", "destroy_postgres",
]
