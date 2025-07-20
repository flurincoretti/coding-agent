import click

from coding_agent.core import loop


@click.command(context_settings=dict(help_option_names=["-h", "--help"]))
def main() -> None:
    """
    Start an interactive chat session with Claude.
    """
    loop()


if __name__ == "__main__":
    main()
