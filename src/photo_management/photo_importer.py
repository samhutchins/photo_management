from __future__ import annotations

import hashlib
import pickle
from functools import cached_property
from itertools import zip_longest
from pathlib import Path

import rich
import rich.progress
from rich.table import Table

type Checksum = str
type Filename = str

DATA_FILE = "library.pickle"


class PhotoImporter:
    __all_extensions: set[str] = {".jpg", ".jpeg", ".heic", ".mov", ".mp4", ".avi"}

    def __init__(self, *, library_path: Path, debug: bool = False) -> None:
        self.library_path = library_path
        self.debug = debug

    @cached_property
    def library_checksums(self) -> dict[Checksum, Filename]:
        if self.debug:
            print("Loading library checksums")

        pickle_path = self.library_path / DATA_FILE
        library: dict[Checksum, Filename]
        if pickle_path.exists():
            with open(pickle_path, "rb") as f:
                library = pickle.load(f)
        else:
            library = self.__calculate_checksums(self.library_path)
            with open(pickle_path, "wb") as f:
                pickle.dump(library, f)

        if self.debug:
            rich.print(library)

        return library

    def import_photos(
        self, include_heic: bool, convert_heic: bool, include_video: bool
    ) -> None:
        print("import")

    def verify_library(self) -> None:
        checksums_file = self.library_path / DATA_FILE
        if checksums_file.exists():
            with open(checksums_file, "rb") as f:
                existing_checksums: dict[Filename, list[Checksum]] = self.__flip(pickle.load(f))

            new_checksums: dict[Filename, list[Checksum]] = self.__flip(self.__calculate_checksums(self.library_path))

            checksum_changed: set[str] = set()
            present_in_db_but_not_disk: set[str] = set()
            present_in_disk_but_not_db: set[str] = set()

            all_filenames = set(existing_checksums.keys())
            all_filenames.update(new_checksums.keys())

            for filename in all_filenames:
                if (
                    filename in existing_checksums
                    and filename in new_checksums
                    and not set(existing_checksums[filename]).intersection(new_checksums[filename])
                ):
                    checksum_changed.add(filename)
                elif filename in existing_checksums and filename not in new_checksums:
                    present_in_db_but_not_disk.add(filename)
                elif filename not in existing_checksums and filename in new_checksums:
                    present_in_disk_but_not_db.add(filename)

            if (
                checksum_changed
                or present_in_db_but_not_disk
                or present_in_disk_but_not_db
            ):
                table = Table(title="Changes detected")
                table.add_column("Present on disk but not database")
                table.add_column("Checksum changed")
                table.add_column("Present in database but not on disk")

                for on_disk, checksum_change, in_db in zip_longest(
                    present_in_disk_but_not_db,
                    checksum_changed,
                    present_in_db_but_not_disk,
                    fillvalue="",
                ):
                    table.add_row(on_disk, checksum_change, in_db)

                rich.print(table)
            else:
                print("No changes")
        else:
            print("No database to compare against")

    def __calculate_checksums(self, path: Path) -> dict[Checksum, Filename]:
        checksums: dict[Checksum, Filename] = dict()
        existing_photos = [
            file
            for file in path.rglob("*")
            if file.suffix.lower() in self.__all_extensions
        ]

        for photo in rich.progress.track(
            existing_photos, description="Calculating checksums..."
        ):
            #  TODO this needs to be a relative path, not just the filename
            #  TODO swap keys and values?
            checksums[self.__calculate_checksum(photo)] = photo.name

        return checksums

    def __calculate_checksum(self, file: Path) -> str:
        hash_func = hashlib.sha256()
        with open(file, "rb") as f:
            hash_func.update(f.read())

        return hash_func.hexdigest()

    def __flip(self, dictionary: dict[Checksum, Filename]) -> dict[Filename, list[Checksum]]:
        flipped: dict[Filename, list[Checksum]] = dict()
        for key, value in dictionary.items():
            values: list[Filename] = flipped.get(value, list())
            values.append(key)
            flipped[value] = values

        return flipped

