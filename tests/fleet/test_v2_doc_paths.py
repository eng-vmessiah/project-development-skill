"""TDD contract for the offline V2 documentation path/link checker."""
from __future__ import annotations

import json
from pathlib import Path
import importlib.util


_MODULE_PATH = Path(__file__).parents[2] / "scripts" / "pd_fleet" / "v2_doc_paths.py"
_spec = importlib.util.spec_from_file_location("v2_doc_paths", _MODULE_PATH)
assert _spec and _spec.loader
v2_doc_paths = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v2_doc_paths)


def make_repo(tmp_path: Path, text: str) -> Path:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    doc = root / ".spec" / "pd-fleet-orchestration-v2"
    doc.mkdir(parents=True)
    (doc / "PLAN.md").write_text(text, encoding="utf-8")
    return root


def test_valid_create_exact_allowed_and_anchor_is_deterministic(tmp_path: Path) -> None:
    root = make_repo(
        tmp_path,
        """# Plan\n\n## T2-17 — Docs\n- **Exact files:** `new.md`, `existing.md`\n- **Allowed paths:** `new.md`, `existing.md`\n- **Create:** `new.md`\n\n## Safety\n\n[anchor](#safety)\n""",
    )
    (root / "existing.md").write_text("ok", encoding="utf-8")
    first = v2_doc_paths.check_repo(root)
    second = v2_doc_paths.check_repo(root)
    assert first == second
    assert first["violations"] == []
    assert json.dumps(first, ensure_ascii=False, sort_keys=True, separators=(",", ":")) == json.dumps(second, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def test_missing_create_from_wrong_task_and_v1_are_violations(tmp_path: Path) -> None:
    root = make_repo(
        tmp_path,
        """# Plan\n## T2-01\n- **Create:** `missing.py`\n## T2-17\n- **Exact files:** `missing.py`, `.spec/pd-fleet-orchestration/STATE.md`, `other.md`\n- **Allowed paths:** `other.md`\n""",
    )
    result = v2_doc_paths.check_repo(root)
    codes = {item["code"] for item in result["violations"]}
    assert "CREATE_OWNERSHIP" in codes
    assert "V1_FORBIDDEN" in codes
    assert "MISSING_PATH" in codes


def test_broken_anchor_traversal_and_escape_are_rejected(tmp_path: Path) -> None:
    root = make_repo(tmp_path, """# Plan\n## T2-17\n[bad](#does-not-exist) [escape](../../../outside.md) [out](https://example.invalid/x)\n""")
    result = v2_doc_paths.check_repo(root)
    codes = {item["code"] for item in result["violations"]}
    assert {"BROKEN_ANCHOR", "TRAVERSAL", "EXTERNAL_LINK"} <= codes


def test_exit_codes_cover_valid_violations_and_invalid_root(tmp_path: Path, capsys) -> None:
    root = make_repo(tmp_path, "# Plan\n## T2-17\n")
    assert v2_doc_paths.main([str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["violations"] == []
    bad = make_repo(tmp_path / "bad", "# Plan\n## T2-17\n[bad](missing.md)\n")
    assert v2_doc_paths.main([str(bad)]) == 1
    assert v2_doc_paths.main([str(tmp_path / "nope")]) == 2


def test_mixed_exact_paths_only_mark_the_local_item_as_create(tmp_path: Path) -> None:
    root = make_repo(tmp_path, """# Plan\n## T2-17\n- **Exact files:** `created.md` (Create), `missing.md`\n""")
    (root / "created.md").write_text("ok", encoding="utf-8")
    result = v2_doc_paths.check_repo(root)
    assert any(v["code"] == "MISSING_PATH" and "missing.md" in v["detail"] for v in result["violations"])
    assert not any(v["code"] == "MISSING_PATH" and "created.md" in v["detail"] for v in result["violations"])


def test_symlink_root_and_scanned_document_fail_closed(tmp_path: Path) -> None:
    real = make_repo(tmp_path, "# Plan\n## T2-17\n")
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(real, target_is_directory=True)
    assert {v["code"] for v in v2_doc_paths.check_repo(linked_root)["violations"]} == {"SYMLINK_ROOT"}
    assert v2_doc_paths.main([str(linked_root)]) == 2

    outside = tmp_path / "outside.md"
    outside.write_text("# outside\n", encoding="utf-8")
    doc = real / ".spec" / "pd-fleet-orchestration-v2" / "PLAN.md"
    doc.unlink()
    doc.symlink_to(outside)
    result = v2_doc_paths.check_repo(real)
    assert any(v["code"] == "SYMLINK_DOC" for v in result["violations"])


def test_duplicate_create_ownership_is_reported(tmp_path: Path) -> None:
    root = make_repo(tmp_path, """# Plan\n## T2-01\n- **Create:** `shared.md`\n## T2-17\n- **Create:** `shared.md`\n""")
    result = v2_doc_paths.check_repo(root)
    assert any(v["code"] == "CREATE_OWNERSHIP" for v in result["violations"])
