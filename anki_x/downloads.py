"""Verified inbound downloads and extraction shared by setup and updating."""

import hashlib
import os
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path


class DownloadError(RuntimeError):
    pass


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_verified(url, checksum, destination, progress=None, cancelled=None):
    destination = Path(destination)
    if urllib.parse.urlsplit(url).scheme != "https":
        raise DownloadError("下载地址必须使用 HTTPS。")
    if len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum.lower()):
        raise DownloadError("下载清单缺少有效校验值。")
    if destination.exists() and sha256(destination) == checksum.lower():
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".download-", dir=destination.parent)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "anki-x-setup"})
        digest, received = hashlib.sha256(), 0
        with urllib.request.urlopen(request, timeout=30) as response, os.fdopen(fd, "wb") as stream:
            fd = None
            total = int(response.headers.get("Content-Length", 0))
            if total > 2 * 1024 ** 3:
                raise DownloadError("下载文件超出允许大小。")
            while chunk := response.read(256 * 1024):
                if cancelled and cancelled():
                    raise DownloadError("下载已取消。")
                received += len(chunk)
                if received > 2 * 1024 ** 3:
                    raise DownloadError("下载文件超出允许大小。")
                stream.write(chunk)
                digest.update(chunk)
                if progress:
                    progress(received, total)
        if digest.hexdigest() != checksum.lower():
            raise DownloadError("下载校验失败，请重新下载。")
        os.replace(temporary, destination)
        return destination
    finally:
        if fd is not None:
            os.close(fd)
        Path(temporary).unlink(missing_ok=True)


def extract_zip(archive, destination):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as source:
        for item in source.infolist():
            path = destination / item.filename
            if not path.resolve().is_relative_to(destination) or "\\" in item.filename:
                raise DownloadError("压缩包包含无效路径。")
            mode = item.external_attr >> 16
            if mode & 0o170000 == 0o120000:
                raise DownloadError("ZIP 包含不支持的符号链接。")
        source.extractall(destination)
        for item in source.infolist():
            mode = item.external_attr >> 16
            if mode and not item.is_dir() and os.name != "nt":
                os.chmod(destination / item.filename, mode & 0o755)


def extract_tar_zst(archive, destination):
    import zstandard
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with Path(archive).open("rb") as compressed:
        with zstandard.ZstdDecompressor().stream_reader(compressed) as stream:
            with tarfile.open(fileobj=stream, mode="r|") as source:
                source.extractall(destination, filter="data")
