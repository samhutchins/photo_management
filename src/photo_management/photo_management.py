from typer import Typer

app = Typer()


@app.command()
def main() -> None:
    print("Hello, World!")
