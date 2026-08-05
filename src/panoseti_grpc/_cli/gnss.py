from __future__ import annotations

import sys
from typing import Annotated

import typer

app = typer.Typer(help="Pass arguments through to the U-Blox F9T GNSS orchestrator.")


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
    args: Annotated[list[str] | None, typer.Argument(help="Arguments passed to ublox-f9t")] = None,
) -> None:
    del ctx

    try:
        from ublox_f9t.cli import main
    except ImportError:
        print(
            "GNSS support is not installed. Install the panoseti-grpc GNSS extra: "
            "uv tool install 'panoseti-grpc[gnss]'",
            file=sys.stderr,
        )
        raise typer.Exit(2)

    argv = list(args or []) or ["--help"]
    try:
        code = main(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    raise typer.Exit(code)
