import contextlib
import itertools
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

EXAMPLES_DIR = Path(__file__).parent / "examples"
TOC_EXAMPLES_DIR = Path(__file__).parent / "examples-toc"


@contextlib.contextmanager
def workdir(src: Path) -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as tempdir:
        shutil.copytree(src, tempdir, dirs_exist_ok=True)
        yield Path(tempdir)


# Smoke test the base copy worked as expected
def test_smoke() -> None:
    with workdir(EXAMPLES_DIR) as test_dir:
        assert take_snapshot(EXAMPLES_DIR) == take_snapshot(test_dir)


def take_snapshot(ref: Path) -> str:
    return "\n".join(
        itertools.chain.from_iterable(
            [
                f">>>> START FILE: {x.relative_to(ref)}",
                x.read_text(),
                "<<<< END FILE",
            ]
            for x in ref.glob("**/*.md")
        )
    )


def test_examples(snapshot: object) -> None:
    with workdir(EXAMPLES_DIR) as test_dir:
        subprocess.run(
            ["python", "-m", "mdindex", str(test_dir), "-r"],
            cwd=test_dir,
            check=True,
            capture_output=True,
        )

        assert snapshot == take_snapshot(test_dir)


def test_examples_no_recursive(snapshot: object) -> None:
    with workdir(EXAMPLES_DIR) as test_dir:
        subprocess.run(
            ["python", "-m", "mdindex", str(test_dir)],
            cwd=test_dir,
            check=True,
            capture_output=True,
        )

        assert snapshot == take_snapshot(test_dir)


def test_ignore(snapshot: object) -> None:
    with workdir(EXAMPLES_DIR) as test_dir:
        subprocess.run(
            [
                "python",
                "-m",
                "mdindex",
                str(test_dir / "foo"),
                "-r",
                # Will ignore everything under deep
                "--ignore=**/deep/**",
                # Will not ignore two.md as that's not a match
                "--ignore=two",
            ],
            cwd=test_dir / "foo",
            check=True,
            capture_output=True,
        )

        assert snapshot == take_snapshot(test_dir / "foo")


def test_toc(snapshot: object) -> None:
    with workdir(TOC_EXAMPLES_DIR) as test_dir:
        subprocess.run(
            [
                "python",
                "-m",
                "mdindex",
                str(test_dir),
                "-r",
                "--toc",
            ],
            cwd=test_dir,
            check=True,
            capture_output=True,
        )

        assert snapshot == take_snapshot(test_dir)
