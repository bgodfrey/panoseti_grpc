from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(help="Pass arguments through to the U-Blox F9T GNSS orchestrator.")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _orchestrator_script() -> Path:
    return _repo_root() / "gnss_config" / "U-Blox_F9T_Config" / "gnss_scripts" / "gnss_orchestrator.py"


def _ublox_repo() -> Path:
    return _repo_root() / "gnss_config" / "U-Blox_F9T_Config"


@app.command(
    name="gnss",
    context_settings={
        "allow_extra_args": True,
        "ignore_unknown_options": True,
    },
    add_help_option=False,
    help="Pass arguments through to the U-Blox F9T GNSS orchestrator.",
)
def passthrough(
    ctx: typer.Context,
    args: Annotated[list[str] | None, typer.Argument(help="Arguments passed to gnss_orchestrator.py")] = None,
) -> None:
    del ctx

    script = _orchestrator_script()
    if not script.exists():
        print(
            f"GNSS orchestrator not found at {script}. "
            "Run `git submodule update --init --recursive` from the panoseti_grpc checkout.",
            file=sys.stderr,
        )
        raise typer.Exit(2)

    argv = list(args or []) or ["--help"]
    repo = _ublox_repo()
    repo_path = str(repo)
    if repo_path not in sys.path:
        sys.path.insert(0, repo_path)

    from gnss_scripts.gnss_orchestrator import main

    try:
        code = main(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    raise typer.Exit(code)
