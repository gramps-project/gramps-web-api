"""Command line interface for the Gramps web API."""


import click
import os

from .app import create_app
from .const import ENV_CONFIG_FILE


@click.group("cli")
@click.option("--config", help="Set the path to the config file")
@click.pass_context
def cli(ctx, config):
    """Gramps web API command line interface."""
    os.environ[ENV_CONFIG_FILE] = os.path.abspath(config)
    ctx.obj = create_app()


@cli.command("run")
@click.option("-p", "--port", help="Port to use (default: 5000)", default=5000)
@click.pass_context
def run(ctx, port):
    """Run the app."""
    app = ctx.obj
    # threading is disabled to avoid problems with locked databases
    app.run(port=port, threaded=False)


if __name__ == "__main__":
    cli()  # pylint:disable=no-value-for-parameter
