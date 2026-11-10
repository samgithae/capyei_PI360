"""Architecture contracts (T-032, NFR-08). Fails the build on a violation."""

import ast
import shutil
import subprocess
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
APPS = BACKEND / "apps"
# Shared conventions any module may use, besides another module's services.
SHARED = {"api"}


def test_import_linter_contracts_hold():
    exe = shutil.which("lint-imports")
    if exe is None:
        pytest.skip("import-linter not installed")
    result = subprocess.run([exe], cwd=BACKEND, capture_output=True, text=True)  # noqa: S603
    assert result.returncode == 0, result.stdout + result.stderr


def _imported_modules(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield from (f"{node.module}.{alias.name}" for alias in node.names)


def cross_module_violations(apps_dir=APPS):
    """Imports of another module's internals: anything but apps.<other>.services."""
    found = []
    for path in apps_dir.rglob("*.py"):
        own = path.relative_to(apps_dir).parts[0]
        for name in _imported_modules(ast.parse(path.read_text(), str(path))):
            parts = name.split(".")
            if parts[0] != "apps" or len(parts) < 2 or parts[1] in {own, *SHARED}:
                continue
            if len(parts) == 2 or parts[2] != "services":
                found.append(f"{path.relative_to(apps_dir.parent)} imports {name}")
    return sorted(set(found))


def test_modules_use_only_each_others_services():
    assert cross_module_violations() == []


def test_every_module_has_a_service_interface():
    missing = [
        p.name
        for p in APPS.iterdir()
        if p.is_dir()
        and p.name not in SHARED
        and not p.name.startswith("__")
        and not (p / "services.py").exists()
    ]
    assert missing == []


def test_scanner_catches_a_model_import(tmp_path):
    """The scanner itself must flag a cross-module models import."""
    fake = tmp_path / "apps"
    (fake / "referrals").mkdir(parents=True)
    (fake / "referrals" / "x.py").write_text(
        "from apps.participants.models import Participant\n"
        "from apps.participants import services\n"
        "from apps.api.problems import problem\n"
    )
    assert cross_module_violations(fake) == [
        "apps/referrals/x.py imports apps.participants.models.Participant",
    ]
