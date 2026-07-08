from __future__ import annotations

import os
import sys
from pathlib import Path

import click


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _orchestrator_script() -> Path:
    return _repo_root() / "gnss_config" / "U-Blox_F9T_Config" / "gnss_scripts" / "gnss_orchestrator.py"


@click.command(
    context_settings={
        "allow_extra_args": True,
        "ignore_unknown_options": True,
    },
    add_help_option=False,
    help="Pass arguments through to the U-Blox F9T GNSS orchestrator.",
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def app(ctx: click.Context, args: tuple[str, ...]) -> None:
    del ctx

    script = _orchestrator_script()
    if not script.exists():
        click.echo(
            f"GNSS orchestrator not found at {script}. "
            "Run `git submodule update --init --recursive` from the panoseti_grpc checkout.",
            err=True,
        )
        raise click.exceptions.Exit(2)

    argv = list(args) or ["--help"]
    os.chdir(script.parent)
    os.execv(sys.executable, [sys.executable, str(script), *argv])
