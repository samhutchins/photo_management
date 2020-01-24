#!/usr/bin/env python3

from argparse import ArgumentParser
from datetime import datetime
from os.path import basename
from pathlib import Path
from subprocess import run, PIPE
from sys import exit
from shutil import copy2

import json
import os
import hashlib
import pickle

version = f"""\
{basename(__file__)} 2020.1
Copyright (c) 2020 Sam Hutchins\
"""

help = f"""\
Allows you to import photos, and optionally videos, into a specified photo
library.

Usage: {basename(__file__)} COMMAND [OPTIONS...]

Commands:
  import        import photos/videos from the current working directory to the
                  photo library
  verify        recalculate checksums of everything in the photo library, and
                  print changes

Library options:
-l, --library   specify the location of your photo library
                  (default: ~/Pictures/)
    --include-heic
                include heic files when scanning for files to import.
    --convert-heic
                convert heic files to the more compatible jpeg format
                  (requires `magick`)
    --include-video
                include videos when scanning for files to import

Other options:
-h, --help      print this message and exit
    --version   print version information and exit

Requires `exiftool`. `magick` is required for --convert-heic\
"""


def main():
    args = define_args()
    validate_tools(args)

    if args.command == "verify":
        verify_library(args)
    elif args.command == "import":
        import_to_library(args)


def define_args():
    parser = ArgumentParser(add_help=False)
    parser.add_argument("command", metavar="COMMAND", nargs="?")
    parser.add_argument("-l", "--library", action="store")
    parser.add_argument("--include-heic", action="store_true")
    parser.add_argument("--convert-heic", action="store_true")
    parser.add_argument("--include-video", action="store_true")

    parser.add_argument("--version", action="store_true")
    parser.add_argument("-h", "--help", action="store_true")

    args = parser.parse_args()

    if args.help:
        print(help)
        exit()

    if args.version:
        print(version)
        exit()

    if not args.command:
        exit(f"Please specify a command. Try {basename(__file__)} --help for more information")

    if args.command not in ["import", "verify"]:
        exit(f"{args.command} is not a valid command. Try {basename(__file__)} --help for more information")

    if not args.library:
        args.library = str(Path.home() / "Pictures")

    if not os.path.exists(args.library):
        os.makedirs(args.library)
    
    if not os.path.isdir(args.library):
        exit(f"Not a directory: {args.library}")

    return args


def validate_tools(args):
    tools = [["exiftool", "-ver"]]

    if args.convert_heic:
        tools.append(["magick", "-version"])

    for tool in tools:
        try:
            run(tool, stdout=PIPE, stderr=PIPE).check_returncode()
        except:
            exit(f"Unable to find {tool[0]}")


def verify_library(args):
    library_checksums = init_library(args.library)
    print("Re-calculating checksums...")
    library_files = collect_files(args.library, [".jpg", ".jpg", ".heic", ".mov", ".mp4", ".avi"])
    new_checksums = {}
    for file in library_files:
        new_checksums[file["checksum"]] = basename(file["SourceFile"])

    library_checksums = flip_dict(library_checksums)
    new_checksums = flip_dict(new_checksums)

    library_has_changed = False
    for key, value in new_checksums.items():
        library_sum = library_checksums.get(key, [])
        if value[0] not in library_sum:
            library_has_changed = True
            print(f"{key} has changed since import")

    if not library_has_changed:
        print("No changes")


def import_to_library(args):
    library_checksums = init_library(args.library)

    print("Scanning for files to import...")
    extensions = [".jpg", ".jpeg"]
    extensions.extend([".heic"] if args.include_heic else [])
    extensions.extend([".mov", ".mp4", ".avi"] if args.include_video else [])

    unfiltered_files = collect_files(os.getcwd(), extensions)
    seen = set()
    files_to_import = []
    for file in unfiltered_files:
        if file["checksum"] not in seen and file["checksum"] not in library_checksums:
            files_to_import.append(file)
            seen.add(file["checksum"])
    
    if files_to_import:
        print(f"Importing {len(files_to_import)} files...")
        for file_info in files_to_import:
            file = file_info["SourceFile"]

            date_tags = ["DateTimeOriginal", "CreateDate", "ModifyDate"]
            date_info = ""
            for tag in date_tags:
                date_info = file_info.get(tag, "")
                if "|" in date_info:
                    break

            if "|" in date_info:
                try:
                    year, month, filename = date_info.split("|")
                except Exception as e:
                    print(file_info)
                    print(e)
                    exit("Bye!")
                
                folder = os.path.join(args.library, year, month)
                library_checksums.update(import_file(file_info, folder, filename, args))
            else:
                print(f"WARNING: No date found in {file}")
                folder = os.path.join(args.library, "errors")
                filename = os.path.splitext(basename(file))[0]
                library_checksums.update(import_file(file_info, folder, filename, args))

        update_library(args.library, library_checksums)
    else:
        print("No files to import")


def import_file(file_info, target_dir, desired_filename, args):
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    file = file_info["SourceFile"]
    ext = os.path.splitext(file)[1].lower()
    desired_ext = ".jpg" if ext == ".heic" and args.convert_heic else ext

    deduped_filename = desired_filename + desired_ext
    suffix = "a"
    while os.path.exists(os.path.join(target_dir, deduped_filename)):
        deduped_filename = desired_filename + suffix + desired_ext
        suffix = chr(ord(suffix) + 1)

    destination = os.path.join(target_dir, deduped_filename)
    checksums = {file_info["checksum"]: deduped_filename}
    if ext == ".heic" and args.convert_heic:
        command = ["magick", "convert", file, destination]
        try:
            run(command, stdout=PIPE, stderr=PIPE).check_returncode()
        except:
            exit(f"Failed to invoke {command[0]}")
        
        checksums[calculate_checksum(destination)] = deduped_filename
    else:
        copy2(file, destination)

    return checksums


def collect_files(directory, extensions):
    ext_options = []
    for ext in extensions:
        ext_options.extend(["-ext", ext])

    command = [
        "exiftool",
        "-j", # json output
        "-AllDates", 
        "-d", "%Y|%m - %B|%Y-%m-%d %H-%M-%S", # date format. Later on we split on `|` to get the directory structure and filename
        "-r" # recursively scan
    ] + ext_options + [ # filter by extentions
        directory
    ]

    try:
        output = run(command, stdout=PIPE, stderr=PIPE)
        output.check_returncode()
    except Exception as e:
        print(output.stderr.decode("ascii"))
        exit("Failed to scan for files")

    if output.stdout:
        files = json.loads(output.stdout)

        for file in files:
            file["SourceFile"] = os.path.abspath(file["SourceFile"])
            file["checksum"] = calculate_checksum(file["SourceFile"])
    else:
        files = []

    return files


def init_library(library_location):
    pickle_path = os.path.join(library_location, "library.pickle")

    if os.path.exists(pickle_path):
        with open(pickle_path, "rb") as f:
            checksums = pickle.load(f)
    else:
        print("Calculating checksums for existing photos...")
        checksums = {}
        existing_photos = collect_files(library_location, [".jpg", ".jpeg", ".heic", ".mov", ".mp4", ".avi"])
        for existing_photo in existing_photos:
            checksums[existing_photo["checksum"]] = existing_photo["SourceFile"]

        with open(pickle_path, "wb") as f:
            pickle.dump(checksums, f)

    return checksums


def update_library(library_location, checksums):
    pickle_path = os.path.join(library_location, "library.pickle")
    with open(pickle_path, "wb") as f:
        pickle.dump(checksums, f)


def calculate_checksum(file):
    hash_func = hashlib.sha256()
    with open(file, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_func.update(chunk)

    return hash_func.hexdigest()


def flip_dict(dict_to_flip):
    flipped_dict = {}

    for key, value in dict_to_flip.items():
        flipped_value = flipped_dict.get(value, [])
        flipped_value.append(key)
        flipped_dict[value] = flipped_value

    return flipped_dict


if __name__ == "__main__":
    main()
