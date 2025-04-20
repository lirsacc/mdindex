"""Create index files and table of contents for collections of markdown files."""

from __future__ import annotations

import argparse
import fnmatch
import functools
import logging
import re
import sys
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


__version__ = "0.1.0"

WARNING_FILE = "<!-- WARN: This file is auto-generated. Do not edit manually. -->"
WARNING_COMMAND = "<!-- command: {command} -->"
WARNING_SECTION = "<!-- WARN: This section is auto-generated. Do not edit manually. -->"

GENERATED_INDEX_START_MARKER = "<!-- mdindex:index:start -->"
GENERATED_INDEX_END_MARKER = "<!-- mdindex:index:end -->"

GENERATED_TOC_START_MARKER = "<!-- mdindex:toc:start -->"
GENERATED_TOC_END_MARKER = "<!-- mdindex:toc:end -->"

type Action = Literal["create", "recreate", "update"]

logger = logging.getLogger()


class ExitError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Context:
    index_file: str = "README.md"
    command: str | None = None
    max_depth: int = 2


@dataclass(frozen=True, slots=True)
class Node:
    path: Path
    files: list[Path] = field(default_factory=list)
    children: list[Node] = field(default_factory=list)


def build_tree(directory: Path, index_file: str, *, ignored_globs: Sequence[str] = ()) -> Node:
    """Collect all files to consider in a basic tree structure."""
    root = Node(directory)

    for x in directory.glob("**/*.md"):
        if any(fnmatch.fnmatch(str(x), pattern) for pattern in ignored_globs):
            continue

        if x.name == index_file:  # Don't include index files at this stage.
            continue

        section = root
        *parents, _ = x.relative_to(directory).parts

        for parent in parents:
            if not (child := next((x for x in section.children if x.path.name == parent), None)):
                child = Node(section.path / parent)
                section.children.append(child)
            section = child

        section.files.append(x)

    return root


@functools.lru_cache(maxsize=128)
def get_lines(filepath: Path) -> list[str]:
    return [x.rstrip("\n") for x in filepath.open().readlines()]


@functools.lru_cache(maxsize=128)
def is_generated(filepath: Path) -> bool:
    return any(GENERATED_INDEX_START_MARKER in x for x in get_lines(filepath))


@functools.lru_cache(maxsize=128)
def extract_title(filepath: Path) -> str | None:
    lines = get_lines(filepath)
    for a, b in zip(lines, [*lines[1:], None]):
        if a.startswith("# "):
            return a[2:].strip()
        if b and re.match(r"==+", b) and (inner := a.strip()):
            return inner
    return None


def titlecase(value: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])|[-_]", " ", value).title()


def get_title(filepath: Path) -> str:
    return extract_title(filepath) or titlecase(filepath.stem)


def get_section_title(path: Path, ctx: Context) -> str:
    index = path / ctx.index_file
    if index.exists() and (extracted := extract_title(index)):
        return extracted
    return titlecase(path.name)


def find_marker_line(filepath: Path, marker: str) -> int | None:
    positions = [i for i, x in enumerate(get_lines(filepath)) if marker in x]
    if not positions:
        return None

    if len(positions) > 1:
        msg = f"Multiple markers {marker} found in {filepath}"
        raise ExitError(msg)

    return positions[0]


def find_index_section(filepath: Path) -> tuple[int, int] | None:
    start = find_marker_line(filepath, GENERATED_INDEX_START_MARKER)
    end = find_marker_line(filepath, GENERATED_INDEX_END_MARKER)
    if start is None or end is None:
        return None
    if end <= start:
        msg = f"{GENERATED_INDEX_END_MARKER} should be after {GENERATED_INDEX_START_MARKER} in {filepath}"
        raise ExitError(msg)
    return start, end


def index_markdown(section: Node, ctx: Context, *, max_depth: int) -> str:
    directory = section.path

    def _write_section(section: Node, level: int) -> Iterable[str]:
        if level > -1:
            quoted = urllib.parse.quote(str(section.path.relative_to(directory)))
            yield f"{('  ' * level)}- [{get_section_title(section.path, ctx)}](./{quoted})"

        if (level + 1) >= max_depth:
            return

        nested = level + 1

        for x in sorted(section.files):
            title = get_title(x)
            quoted = urllib.parse.quote(str(x.relative_to(directory)))
            yield f"{('  ' * nested)}- [{title}](./{quoted})"

        for y in sorted(section.children, key=lambda x: x.path.name):
            yield from _write_section(y, nested)

    return "\n".join(_write_section(section, -1))


def _warning_details(command: str | None) -> str:
    if command is not None:
        return f"{WARNING_COMMAND.format(command=command)}"
    return ""


def _join_non_empty(lines: Iterable[str]) -> str:
    return "\n".join(x for x in lines if x)


def full_file_markdown(
    section: Node,
    *,
    inner: str,
    command: str | None = None,
) -> str:
    return "\n".join(
        [
            GENERATED_INDEX_START_MARKER,
            f"# {section.path.name}",
            "",
            _join_non_empty([WARNING_FILE, _warning_details(command)]),
            "",
            inner,
            GENERATED_INDEX_END_MARKER,
        ],
    )


def section_markdown(
    *,
    inner: str,
    command: str | None = None,
) -> str:
    return "\n".join(
        [
            GENERATED_INDEX_START_MARKER,
            _join_non_empty([WARNING_SECTION, _warning_details(command)]),
            "",
            inner,
            "",
            GENERATED_INDEX_END_MARKER,
        ],
    )


def generate_index_contents(
    root: Node,
    ctx: Context,
    *,
    recursive: bool = False,
) -> Iterable[tuple[Path, str, Action]]:
    index = index_markdown(root, ctx, max_depth=ctx.max_depth)
    output_file = root.path / ctx.index_file

    if output_file.exists():
        markers = find_index_section(output_file)
        if markers is None:
            logger.info("%s already exists and is not generated by this command", output_file)
        else:
            start, end = markers
            if start == 0:
                contents = full_file_markdown(
                    root,
                    inner=index,
                    command=ctx.command,
                ).rstrip("\n")
                yield output_file, contents + "\n", "recreate"
            else:
                lines = get_lines(output_file)
                before = [x for i, x in enumerate(lines) if i < start]
                after = [x for i, x in enumerate(lines) if i > end]
                inside = section_markdown(inner=index, command=ctx.command)
                contents = "\n".join([*before, inside, *after])

                yield output_file, contents + "\n", "update"
    else:
        contents = full_file_markdown(
            root,
            inner=index,
            command=ctx.command,
        ).rstrip("\n")
        yield output_file, contents + "\n", "create"

    if recursive:
        for x in root.children:
            yield from generate_index_contents(x, ctx, recursive=recursive)


def generate_index_files(
    directory: Path,
    ctx: Context,
    *,
    recursive: bool = False,
    ignored_globs: Sequence[str] = (),
    check: bool = False,
) -> None:
    root = build_tree(directory, ctx.index_file, ignored_globs=ignored_globs)
    summaries = generate_index_contents(root, ctx, recursive=recursive)

    if check:
        fail = False
        for path, content, _ in summaries:
            if not path.is_file() or path.read_text() != content:
                logger.info("%s is not up to date", path)
                fail = True
        if fail:
            if ctx.command:
                logger.info("To update run: %s", ctx.command)
            sys.exit(1)
    else:
        for path, content, action in summaries:
            if not path.is_file() or path.read_text() != content:
                logger.debug("Writing index file at %s (%s)", path, action)
                path.write_text(content)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--verbose", "-v", help="Print debug logs to stderr", action="store_true")

    parser.add_argument("directory", type=Path, default="docs", help="Root directory")
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="README.md",
        required=False,
        help="Index file name",
    )
    parser.add_argument(
        "--command",
        type=str,
        required=False,
        help="Command used for generating the index files",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=3,
        required=False,
        help="Only list files in directories up to <MAX_DEPTH> from each level.",
    )
    parser.add_argument(
        "--recursive",
        "-r",
        action="store_true",
        help="Also generate index files for subfolders recursively.",
    )
    parser.add_argument(
        "--ignore",
        "-i",
        type=str,
        action="append",
        default=[],
        required=False,
        help="Glob patterns to ignore. This applies to input directory and files.",
    )
    parser.add_argument(
        "--check",
        "-c",
        action="store_true",
        help="Check if the index files are up to date.",
    )

    args = parser.parse_args()

    ignored_globs = tuple(args.ignore)

    logger.addHandler(logging.StreamHandler(sys.stderr))
    logger.setLevel(logging.DEBUG if args.verbose else logging.INFO)

    ctx = Context(
        index_file=args.output,
        command=args.command,
        max_depth=args.max_depth,
    )

    try:
        generate_index_files(
            Path(args.directory),
            ctx=ctx,
            ignored_globs=tuple(ignored_globs),
            recursive=args.recursive,
            check=args.check,
        )
    except ExitError as e:
        logger.info(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
