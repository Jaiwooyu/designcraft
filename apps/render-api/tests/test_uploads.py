import stat
import struct
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import pytest

from render_api.config import Settings
from render_api.uploads import InvalidPackage, unpack


def package(tmp_path, entries, **overrides):
    path = tmp_path / "upload.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("input.idml", b"document")
        for name, data in entries:
            archive.writestr(name, data)
    destination = tmp_path / "input"
    destination.mkdir()
    settings = replace(Settings(renderer=Path("unused"), data_dir=tmp_path), **overrides)
    return path, destination, settings


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "/tmp/escape",
        "Links/../../escape",
        "Links\\escape",
        "Links/C:escape",
        "Links/NUL.png",
        "Links/COM¹",
        "Links/dir./image",
        "Links//image",
        "Links/./image",
        "outside.txt",
        "Links/" + "a" * 241,
    ],
)
def test_reject_unsafe_paths(tmp_path, name):
    args = package(tmp_path, [(name, b"data")])
    if "\\" in name:
        # Windows ZipInfo normalizes backslashes; patch both ZIP headers to keep the attack.
        args[0].write_bytes(
            args[0].read_bytes().replace(name.replace("\\", "/").encode(), name.encode())
        )
    with pytest.raises(InvalidPackage):
        unpack(*args)
    assert list(args[1].iterdir()) == []


def test_reject_symlinks(tmp_path):
    info = ZipInfo("Links/image.jpg")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(InvalidPackage, match="special"):
        unpack(*package(tmp_path, [(info, b"../../outside")]))


@pytest.mark.parametrize(
    "entries",
    [
        [("Links/Image", b"a"), ("Links/image", b"b")],
        [("Links/é", b"a"), ("Links/e\u0301", b"b")],
        [("second.idml", b"other")],
    ],
)
def test_reject_ambiguous_packages(tmp_path, entries):
    with pytest.raises(InvalidPackage):
        unpack(*package(tmp_path, entries))


def test_limits_and_lying_directory_count(tmp_path):
    args = package(tmp_path, [("Links/a", b"x" * 100)], max_unpacked_bytes=16)
    with pytest.raises(InvalidPackage, match="size limit"):
        unpack(*args)
    assert list(args[1].iterdir()) == []
    data = bytearray(args[0].read_bytes())
    end = data.rfind(b"PK\x05\x06")
    struct.pack_into("<HH", data, end + 8, 1, 1)
    args[0].write_bytes(data)
    with pytest.raises(InvalidPackage, match="directory"):
        unpack(args[0], args[1], replace(args[2], max_unpacked_bytes=1024))


def test_rejected_zip_request_is_removed(api):
    content = BytesIO()
    with ZipFile(content, "w") as archive:
        archive.writestr("../escape", b"bad")
    with api() as (client, manager):
        response = client.post("/renders", files={"file": ("bad.zip", content.getvalue())})
        assert response.status_code == 400
        assert list(manager.jobs_dir.iterdir()) == []
