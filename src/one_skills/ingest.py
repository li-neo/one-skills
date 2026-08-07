"""Secure source ingestion, normalization, and structural chunking."""

from __future__ import annotations

import ipaddress
import mimetypes
import re
import shutil
import socket
import subprocess
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.etree import ElementTree

from .constants import (
    HTML_SUFFIXES,
    MAX_LOCAL_BYTES,
    MAX_URL_BYTES,
    SUPPORTED_SUFFIXES,
    TEXT_SUFFIXES,
)
from .models import Chunk, SourceDocument
from .utils import sha256_bytes


class IngestionError(RuntimeError):
    """A source could not be ingested without violating safety or truthfulness."""


class _TextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in {"script", "style", "noscript"}:
            self.ignored_depth += 1
        elif tag in {"p", "div", "section", "article", "li", "h1", "h2", "h3", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.ignored_depth:
            self.ignored_depth -= 1
        elif tag in {"p", "div", "section", "article", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.ignored_depth:
            self.parts.append(data)

    def result(self) -> str:
        return normalize_text("".join(self.parts))


class _ValidatedRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        assert_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\t ]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def decode_bytes(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "big5", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise IngestionError("unable to identify source encoding")


def html_to_text(text: str) -> str:
    parser = _TextHTMLParser()
    parser.feed(text)
    return parser.result()


def assert_public_host(hostname: str | None) -> None:
    if not hostname:
        raise IngestionError("URL has no hostname")
    try:
        addresses = {record[4][0] for record in socket.getaddrinfo(hostname, None)}
    except socket.gaierror as exc:
        raise IngestionError(f"cannot resolve hostname: {hostname}") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise IngestionError(f"private or local network target rejected: {hostname} -> {address}")


def assert_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise IngestionError(f"unsupported URL scheme: {parsed.scheme}")
    if parsed.username or parsed.password:
        raise IngestionError("URLs containing credentials are rejected")
    assert_public_host(parsed.hostname)


def _assert_archive_budget(archive: zipfile.ZipFile, path: Path) -> None:
    total = sum(item.file_size for item in archive.infolist())
    if total > MAX_LOCAL_BYTES:
        raise IngestionError(
            f"archive expands beyond {MAX_LOCAL_BYTES} byte safety limit: {path}"
        )


def _docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            _assert_archive_budget(archive, path)
            root = ElementTree.fromstring(archive.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise IngestionError(f"invalid DOCX: {path}") from exc
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = [
        "".join(node.text or "" for node in paragraph.iter(namespace + "t"))
        for paragraph in root.iter(namespace + "p")
    ]
    return normalize_text("\n".join(item for item in paragraphs if item))


def _epub_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            _assert_archive_budget(archive, path)
            names = sorted(
                name for name in archive.namelist() if Path(name).suffix.lower() in HTML_SUFFIXES
            )
            chapters = [html_to_text(decode_bytes(archive.read(name))) for name in names]
    except zipfile.BadZipFile as exc:
        raise IngestionError(f"invalid EPUB: {path}") from exc
    if not chapters:
        raise IngestionError(f"EPUB contains no readable chapters: {path}")
    return normalize_text("\n\n".join(chapters))


def _pdf_text(path: Path) -> str:
    executable = shutil.which("pdftotext")
    if not executable:
        raise IngestionError("PDF ingestion requires Poppler pdftotext")
    try:
        result = subprocess.run(
            [executable, "-layout", str(path), "-"],
            check=False,
            capture_output=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise IngestionError("pdftotext exceeded 120 second safety timeout") from exc
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise IngestionError(f"pdftotext failed: {detail or 'unknown error'}")
    if len(result.stdout) > MAX_LOCAL_BYTES:
        raise IngestionError("PDF extracted text exceeds safety limit")
    return normalize_text(decode_bytes(result.stdout))


def ingest_file(path: Path, access_level: str = "private-local") -> SourceDocument:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise IngestionError(f"source is not a file: {path}")
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise IngestionError(f"unsupported source type: {path.suffix or '<none>'}")
    size = path.stat().st_size
    if size > MAX_LOCAL_BYTES:
        raise IngestionError(f"source exceeds {MAX_LOCAL_BYTES} byte limit: {path}")
    data = path.read_bytes()
    suffix = path.suffix.lower()
    extractor = "plain-text"
    if suffix in TEXT_SUFFIXES:
        text = decode_bytes(data)
    elif suffix in HTML_SUFFIXES:
        text = html_to_text(decode_bytes(data))
        extractor = "html"
    elif suffix == ".docx":
        text = _docx_text(path)
        extractor = "docx-xml"
    elif suffix == ".epub":
        text = _epub_text(path)
        extractor = "epub-html"
    elif suffix == ".pdf":
        text = _pdf_text(path)
        extractor = "pdftotext"
    else:
        raise IngestionError(f"no extractor for: {suffix}")
    text = normalize_text(text)
    warnings = ("extracted text is shorter than 200 characters",) if len(text) < 200 else ()
    media_type = mimetypes.guess_type(path.name)[0] or "text/plain"
    return SourceDocument(
        source=str(path),
        title=path.stem,
        media_type=media_type,
        text=text,
        content_hash=sha256_bytes(data),
        byte_count=size,
        access_level=access_level,
        extractor=extractor,
        warnings=warnings,
    )


def ingest_url(url: str, access_level: str = "public") -> SourceDocument:
    assert_public_url(url)
    request = Request(url, headers={"User-Agent": "one-skills/0.1"})
    opener = build_opener(_ValidatedRedirectHandler())
    try:
        with opener.open(request, timeout=30) as response:
            data = response.read(MAX_URL_BYTES + 1)
            final_url = response.geturl()
            content_type = response.headers.get_content_type()
    except IngestionError:
        raise
    except Exception as exc:
        raise IngestionError(f"URL ingestion failed: {url}: {exc}") from exc
    if len(data) > MAX_URL_BYTES:
        raise IngestionError(f"URL content exceeds {MAX_URL_BYTES} byte limit")
    assert_public_url(final_url)
    decoded = decode_bytes(data)
    text = html_to_text(decoded) if content_type in {"text/html", "application/xhtml+xml"} else normalize_text(decoded)
    title_match = re.search(r"<title[^>]*>(.*?)</title>", decoded, flags=re.I | re.S)
    title = html_to_text(title_match.group(1)) if title_match else Path(urlparse(final_url).path).stem
    return SourceDocument(
        source=final_url,
        title=title or urlparse(final_url).netloc,
        media_type=content_type,
        text=text,
        content_hash=sha256_bytes(data),
        byte_count=len(data),
        access_level=access_level,
        extractor="url-html" if "html" in content_type else "url-text",
        warnings=("network source is mutable; preserve this captured hash before publishing",),
    )


def expand_sources(values: list[str], access_level: str = "private-local") -> list[SourceDocument]:
    documents: list[SourceDocument] = []
    errors: list[str] = []
    for value in values:
        if value.startswith(("http://", "https://")):
            try:
                documents.append(ingest_url(value, "public"))
            except IngestionError as exc:
                errors.append(str(exc))
            continue
        path = Path(value).expanduser()
        candidates = [path]
        if path.is_dir():
            candidates = sorted(
                item
                for item in path.rglob("*")
                if item.is_file() and item.suffix.lower() in SUPPORTED_SUFFIXES
            )
        for candidate in candidates:
            try:
                documents.append(ingest_file(candidate, access_level))
            except IngestionError as exc:
                errors.append(str(exc))
    if not documents:
        details = "\n".join(f"- {error}" for error in errors)
        raise IngestionError(f"no source was ingested\n{details}".rstrip())
    return documents


def _line_locator(source: str, line_number: int) -> str:
    if urlparse(source).scheme in {"http", "https"}:
        return source
    if "#" not in source:
        return f"{source}#L{line_number}"
    base, fragment = source.split("#", 1)
    fragment = fragment.rstrip("-")
    return f"{base}#{fragment}-L{line_number}" if fragment else f"{base}#L{line_number}"


def structural_chunks(
    document: SourceDocument,
    document_id: str,
    document_version: int,
    target_characters: int = 1800,
) -> list[Chunk]:
    """Split on headings/paragraphs while retaining stable source locators."""
    blocks: list[tuple[str, str, int]] = []
    section = document.title
    buffer: list[str] = []
    start_line = 1
    current_size = 0

    def flush() -> None:
        nonlocal buffer, current_size, start_line
        text = "\n\n".join(buffer).strip()
        if text:
            blocks.append((section, text, start_line))
        buffer = []
        current_size = 0

    for line_number, line in enumerate(document.text.splitlines(), start=1):
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.+)$", line)
        if heading:
            flush()
            section = heading.group(1).strip()
            start_line = line_number
            continue
        paragraph = line.strip()
        if not paragraph:
            continue
        if not buffer:
            start_line = line_number
        if current_size and current_size + len(paragraph) > target_characters:
            flush()
            start_line = line_number
        buffer.append(paragraph)
        current_size += len(paragraph)
    flush()

    chunks: list[Chunk] = []
    for ordinal, (section_path, text, line_number) in enumerate(blocks):
        content_hash = sha256_bytes(text.encode("utf-8"))
        chunks.append(
            Chunk(
                id="chunk-"
                + sha256_bytes(
                    f"{document_id}:{document_version}:{ordinal}:{content_hash}".encode()
                )[:24],
                document_id=document_id,
                document_version=document_version,
                section_path=section_path,
                ordinal=ordinal,
                text=text,
                content_hash=content_hash,
                access_level=document.access_level,
                source_locator=_line_locator(
                    document.source_uri or document.source,
                    line_number,
                ),
                source_key=document.source_uri or document.source,
                independence_group=document.independence_group
                or document.source_uri
                or document.source,
                authority=document.authority,
                source_role=document.source_role,
            )
        )
    return chunks
