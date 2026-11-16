"""Bounded package extraction; never use an uploaded name as a host path."""

import stat
import struct
import unicodedata
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile

from .config import Settings

CHUNK = 1024 * 1024
RESERVED = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in "123456789¹²³"
}


class InvalidPackage(ValueError):
    pass


def safe_parts(name: str) -> list[str]:
    parts = name.rstrip("/").split("/")
    if (
        len(name) > 240
        or len(parts) > 16
        or any(
            not part
            or part in (".", "..")
            or part.endswith((" ", "."))
            or any(ord(c) < 32 or c in '<>:"\\|?*' for c in part)
            or part.split(".", 1)[0].upper() in RESERVED
            for part in parts
        )
    ):
        raise InvalidPackage("Unsafe or excessively long archive path")
    return parts


def check_directory(path: Path, limit: int):
    """Bound the central directory before ZipFile allocates an entry object per file.

    ZIP64/multi-disk packages are intentionally unsupported by this upload boundary.
    The nested IDML itself is left to the renderer's IDML parser.
    """
    size = path.stat().st_size
    with path.open("rb") as stream:
        stream.seek(max(0, size - 65557))
        tail = stream.read(65557)
        index = tail.rfind(b"PK\x05\x06")
        if index < 0 or len(tail) - index < 22:
            raise InvalidPackage("Not a ZIP package")
        _, disk, start_disk, local_count, count, length, offset, comment = struct.unpack_from(
            "<4s4H2IH", tail, index
        )
        end = size - len(tail) + index
        if (
            disk
            or start_disk
            or local_count != count
            or not 0 < count <= limit
            or length > 2 * MIB
            or offset + length != end
            or index + 22 + comment != len(tail)
        ):
            raise InvalidPackage("ZIP directory exceeds limits or uses an unsupported ZIP layout")
        stream.seek(offset)
        directory = stream.read(length)
    cursor = 0
    actual_count = 0
    while cursor < length:
        if cursor + 46 > length or directory[cursor : cursor + 4] != b"PK\x01\x02":
            raise InvalidPackage("Invalid ZIP directory")
        names, extra, comments = struct.unpack_from("<3H", directory, cursor + 28)
        cursor += 46 + names + extra + comments
        actual_count += 1
        if actual_count > limit:
            raise InvalidPackage("Too many archive entries")
    if cursor != length or actual_count != count:
        raise InvalidPackage("Inconsistent ZIP directory")


MIB = 1024 * 1024


def unpack(path: Path, destination: Path, settings: Settings) -> Path:
    check_directory(path, settings.max_archive_entries)
    seen: set[str] = set()
    files = []
    total = 0
    document = None
    try:
        with ZipFile(path) as archive:
            for info in archive.infolist():
                # ZipInfo normalizes Windows separators and truncates NULs in filename.
                # Validate the original archive name before using its normalized form.
                parts = safe_parts(info.orig_filename)
                key = unicodedata.normalize("NFC", "/".join(parts)).casefold()
                mode = stat.S_IFMT(info.external_attr >> 16)
                if info.compress_type not in (ZIP_STORED, ZIP_DEFLATED):
                    raise InvalidPackage("Only stored or deflated ZIP entries are accepted")
                if key in seen or mode not in (0, stat.S_IFREG, stat.S_IFDIR) or info.flag_bits & 1:
                    raise InvalidPackage(
                        "Duplicate paths, special files and encrypted files are refused"
                    )
                seen.add(key)
                if info.is_dir():
                    if parts[0] not in ("Links", "Document Fonts"):
                        raise InvalidPackage("Only Links and Document Fonts folders are accepted")
                    continue
                if len(parts) == 1 and parts[0].lower().endswith(".idml"):
                    if document is not None:
                        raise InvalidPackage("Upload exactly one IDML document at the package root")
                    document = destination / parts[0]
                elif len(parts) < 2 or parts[0] not in ("Links", "Document Fonts"):
                    raise InvalidPackage(
                        "Package files must be an IDML, Links/* or Document Fonts/*"
                    )
                if info.file_size > 256 * MIB:
                    raise InvalidPackage("An unpacked file exceeds 256 MiB")
                total += info.file_size
                if total > settings.max_unpacked_bytes:
                    raise InvalidPackage("Unpacked package exceeds the size limit")
                files.append((info, destination.joinpath(*parts)))
            if document is None:
                raise InvalidPackage("Upload exactly one IDML document at the package root")
            actual = 0
            for info, target in files:
                target.parent.mkdir(parents=True, exist_ok=True)
                written = 0
                with archive.open(info) as source, target.open("xb") as output:
                    while chunk := source.read(CHUNK):
                        written += len(chunk)
                        actual += len(chunk)
                        if written > info.file_size or actual > settings.max_unpacked_bytes:
                            raise InvalidPackage("Expanded package exceeds the size limit")
                        output.write(chunk)
    except (BadZipFile, NotImplementedError, RuntimeError) as error:
        raise InvalidPackage("Corrupt, encrypted or unsupported ZIP package") from error
    return document
