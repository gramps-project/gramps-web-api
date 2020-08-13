import click

from .api import create_app


@click.group("cli")
@click.pass_context
def cli(ctx):
    """CLI."""
    ctx.obj = create_app()


@cli.command("run")
@click.option("-p", "--port", help="Port to use (default: 5000)", default=5000)
@click.pass_context
def run(ctx, port):
    """Custom CLI command."""
    app = ctx.obj
    app.run(port=port, threaded=False)


if __name__ == "__main__":
    cli()
