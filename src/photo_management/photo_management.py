from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import Annotated

from typer import Typer, Option, Exit

from .photo_importer import PhotoImporter

app = Typer()


importer: PhotoImporter


def __version_callback(print_version: bool) -> None:
    if print_version:
        version = importlib.metadata.version(__package__)
        print(version)
        raise Exit()


@app.callback()
def main(
    library: Annotated[
        Path, Option(file_okay=False, dir_okay=True, resolve_path=True)
    ] = Path.home() / "Pictures",
    debug: Annotated[bool, Option(help="Turn on extra debugging")] = False,
    version: Annotated[
        bool,
        Option(
            help="Print application version and exit",
            is_eager=True,
            callback=__version_callback,
        ),
    ] = False,
) -> None:
    library.mkdir(parents=True, exist_ok=True)

    global importer
    importer = PhotoImporter(library_path=library, debug=debug)
    importer.library_path = library


@app.command(name="import")
def import_(
    include_heic: Annotated[
        bool, Option(help="include heic files when scanning for files to import")
    ] = False,
    include_video: Annotated[
        bool, Option(help="include videos when scanning for files to import")
    ] = False,
) -> None:
    """
    Import photos and videos from the current working directory into the photo library
    """
    importer.import_photos(include_heic, include_video)


@app.command(name="verify")
def verify() -> None:
    """
    Recalculate checksums of everything in the photo library, and print changes
    """
    importer.verify_library()
