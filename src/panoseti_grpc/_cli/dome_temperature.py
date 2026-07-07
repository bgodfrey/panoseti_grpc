from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(
    help="Run the local dome temperature telemetry publisher.",
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    config: Annotated[Path | None, typer.Option(help="Path to DAQ-node TOML config")] = None,
    once: Annotated[bool, typer.Option(help="Publish one sample and exit")] = False,
    no_publish: Annotated[
        bool, typer.Option("--no-publish", help="Read and print payloads without gRPC publish")
    ] = False,
    verbose: Annotated[bool, typer.Option(help="Print Telemetry connection state changes")] = False,
) -> None:
    """Read local dome sensors and publish temperature telemetry."""
    if ctx.invoked_subcommand is not None:
        return

    from panoseti_grpc.dome_heating.dome_telemetry import main as dome_temperature_main

    argv: list[str] = []
    if config is not None:
        argv.extend(["--config", str(config)])
    if once:
        argv.append("--once")
    if no_publish:
        argv.append("--no-publish")
    if verbose:
        argv.append("--verbose")

    raise typer.Exit(code=dome_temperature_main(argv))
