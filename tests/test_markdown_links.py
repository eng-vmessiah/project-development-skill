import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from check_markdown_links import check


def _write(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_valid_relative_link_and_anchor(tmp_path: Path) -> None:
    _write(tmp_path, "docs/target.md", "# Target\n")
    _write(tmp_path, "docs/source.md", "[target](target.md#target)\n")
    assert check(tmp_path, [Path("docs/source.md")]) == []


def test_missing_target(tmp_path: Path) -> None:
    _write(tmp_path, "docs/source.md", "[missing](missing.md)\n")
    assert check(tmp_path, [Path("docs/source.md")]) == [
        "docs/source.md: missing target: missing.md"
    ]


def test_missing_anchor(tmp_path: Path) -> None:
    _write(tmp_path, "docs/target.md", "# Other\n")
    _write(tmp_path, "docs/source.md", "[target](target.md#target)\n")
    assert check(tmp_path, [Path("docs/source.md")]) == [
        "docs/source.md: missing anchor: target.md#target"
    ]


def test_external_and_absolute_targets_are_ignored(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "docs/source.md",
        "[web](https://example.test/x) [mail](mailto:dev@example.test) "
        "[root](/absolute/path) [anchor](#local)\n",
    )
    assert check(tmp_path, [Path("docs/source.md")]) == []


def test_target_escaping_repository_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "docs/source.md", "[escape](../../outside.md)\n")
    assert check(tmp_path, [Path("docs/source.md")]) == [
        "docs/source.md: escapes repository: ../../outside.md"
    ]
