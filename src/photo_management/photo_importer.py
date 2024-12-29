from __future__ import annotations

import hashlib
import pickle
import shutil
from datetime import datetime
from itertools import zip_longest
from pathlib import Path
from typing import Any

import dateutil.parser
import rich
import rich.progress
from exiftool import ExifToolHelper  # type: ignore
from rich.panel import Panel
from rich.table import Table
from typer import Abort

type Checksum = str
type Filename = str

DATA_FILE = "library.pickle"


class PhotoImporter:
    __all_extensions: set[str] = {".jpg", ".jpeg", ".heic", ".mov", ".mp4", ".avi"}

    def __init__(self, *, library_path: Path, debug: bool = False) -> None:
        if not shutil.which("exiftool"):
            print("Unable to locate required tool `exiftool`")
            raise Abort()

        self.library_path = library_path
        self.debug = debug
        self.exiftool = ExifToolHelper()
        self.checksums = self.__init_checksums()

    def import_photos(self, include_heic: bool, include_video: bool) -> None:
        extensions: set[str] = {".jpg", ".jpeg"}
        if include_heic:
            extensions.add(".heic")

        if include_video:
            extensions.update({".mov", ".mp4", ".avi"})

        seen: set[str] = set()
        files_to_import: list[tuple[Path, Checksum]] = list()
        unfiltered_files = [
            file for file in Path.cwd().glob("*") if file.suffix.lower() in extensions
        ]
        for file in rich.progress.track(
            unfiltered_files, description="Scanning for files to import..."
        ):
            checksum = self.__calculate_checksum(file)
            if checksum not in seen and checksum not in self.checksums:
                files_to_import.append((file, checksum))
                seen.add(checksum)

        if files_to_import:
            for file, checksum in rich.progress.track(
                files_to_import, description=f"Importing {len(files_to_import)} files..."
            ):
                new_checksums = self.__import_file(file, checksum)
                if self.debug:
                    rich.print(new_checksums)
                self.checksums.update(new_checksums)

            with open(self.library_path / DATA_FILE, "wb") as f:
                pickle.dump(self.checksums, f)
        else:
            print("No files to import")

    def verify_library(self) -> None:
        checksums_file = self.library_path / DATA_FILE
        if checksums_file.exists():
            with open(checksums_file, "rb") as f:
                existing_checksums: dict[Filename, list[Checksum]] = self.__flip(
                    pickle.load(f)
                )

            new_checksums: dict[Filename, list[Checksum]] = self.__flip(
                self.__calculate_checksums(self.library_path)
            )

            checksum_changed: set[str] = set()
            present_in_db_but_not_disk: set[str] = set()
            present_in_disk_but_not_db: set[str] = set()

            all_filenames = set(existing_checksums.keys())
            all_filenames.update(new_checksums.keys())

            for filename in all_filenames:
                if (
                    filename in existing_checksums
                    and filename in new_checksums
                    and not set(existing_checksums[filename]).intersection(
                        new_checksums[filename]
                    )
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

    def __import_file(
        self, file: Path, source_checksum: Checksum
    ) -> dict[Checksum, Filename]:
        exif_tags: dict[str, Any] = self.exiftool.get_metadata([file], None)[0]

        if self.debug:
            content: str = ""
            for key, value in exif_tags.items():
                content += f"{key}: {value}\n"

            panel = Panel(content, title="Exif Data", expand=False)
            rich.print(panel)

        date_time: datetime | None = None
        for tag in [
            "EXIF:DateTimeOriginal",
            "EXIF:CreateDate",
            "XMP:CreateDate",
            "QuickTime:CreateDate",
        ]:
            try:
                try:
                    date_time = datetime.strptime(exif_tags[tag], "%Y:%m:%d %H:%M:%S")
                except ValueError:
                    date_time = dateutil.parser.parse(exif_tags[tag])

                if self.debug:
                    print(date_time)
                break
            except KeyError:
                if self.debug:
                    print(f"Failed to find tag {tag}")
                continue

        checksums: dict[Checksum, Filename] = dict()
        if date_time:
            folder: Path = (
                self.library_path
                / date_time.strftime("%Y")
                / date_time.strftime("%m - %B")
            )
            stem: str = date_time.strftime("%Y-%m-%d %H-%M-%S")
        else:
            folder = self.library_path / "errors"
            stem = file.stem

        folder.mkdir(parents=True, exist_ok=True)
        ext = file.suffix
        target_file = self.__get_unique_filename(folder, stem, ext)
        checksums[source_checksum] = target_file.name
        shutil.copy2(file, target_file)

        return checksums

    @staticmethod
    def __get_unique_filename(folder: Path, stem: str, ext: str) -> Path:
        target_file: Path = folder / (stem + ext)
        suffix = "a"
        while target_file.exists():
            target_file = target_file.with_stem(stem + suffix)
            suffix = chr(ord(suffix) + 1)

        return target_file

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
            checksums[self.__calculate_checksum(photo)] = photo.name

        return checksums

    def __calculate_checksum(self, file: Path) -> str:
        hash_func = hashlib.sha256()
        with open(file, "rb") as f:
            hash_func.update(f.read())

        return hash_func.hexdigest()

    def __flip(
        self, dictionary: dict[Checksum, Filename]
    ) -> dict[Filename, list[Checksum]]:
        flipped: dict[Filename, list[Checksum]] = dict()
        for key, value in dictionary.items():
            values: list[Filename] = flipped.get(value, list())
            values.append(key)
            flipped[value] = values

        return flipped

    def __init_checksums(self) -> dict[Checksum, Filename]:
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
