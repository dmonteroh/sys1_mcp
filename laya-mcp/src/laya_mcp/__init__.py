from .server import app


def main() -> None:
    app.run()


__all__ = ["app", "main"]
