# Testing Modules with Python Import Path Conflicts

A Python project can have a local `agent/tools/` directory that shadows a venv-installed `tools` package. When a module does `from tools import router_classifier`, the import resolves to the venv's `tools/__init__.py` instead of the local `agent/tools/` directory, causing `ImportError`.

## Solution: Fake the `tools` Module via `sys.modules`

Create a synthetic module using `types.ModuleType`, inject the real local modules as attributes, and insert it into `sys.modules` before importing the module under test.

```python
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def setup_tools_module(monkeypatch, tmp_path):
    """Mock Hermes registry + inject agent/tools as 'tools' module."""

    # Build a fake 'tools' package
    tools_pkg = types.ModuleType("tools")
    tools_pkg.registry = MagicMock()

    # Import the real modules from the local path
    local_tools = str(Path(__file__).parent.parent.parent / "agent" / "tools")
    if local_tools not in sys.path:
        sys.path.insert(0, local_tools)

    import router_classifier as real_rc
    tools_pkg.router_classifier = real_rc

    # Import model_router_state with redirected state path
    state_file = tmp_path / "router-state.json"
    monkeypatch.setattr("model_router_state.STATE_PATH", str(state_file))

    # Clear cached imports so the mock takes effect
    for mod in list(sys.modules.keys()):
        if "model_router_state" in mod:
            del sys.modules[mod]

    import model_router_state as real_mrs
    tools_pkg.model_router_state = real_mrs

    # Inject into sys.modules so 'from tools import ...' resolves here
    monkeypatch.setitem(sys.modules, "tools", tools_pkg)

    return state_file


@pytest.fixture
def router():
    """Import the module under test (after tools module is mocked)."""
    import model_router as mr
    return mr
```

## Key Points

1. **`types.ModuleType("tools")`** creates a package-like object without needing a real `tools/__init__.py`.
2. **Real vs mock:** Import the real local modules as attributes of the fake package so the production logic is tested. Only mock things that cause side effects (e.g., Hermes `registry`).
3. **`monkeypatch.setitem(sys.modules, "tools", tools_pkg)`** is the critical injection — it makes `from tools import ...` resolve to your fake package.
4. **Clean up cached imports** before re-importing modules that were already loaded with the wrong path.
5. **File I/O redirection:** Use `monkeypatch.setattr` before importing to redirect file paths (e.g., state files) to temp locations.

---

## Pattern 2: Framework Not Installed (Mock Everything)

When the module under test imports from a framework that **isn't installed** in the test venv (e.g., `hermes_ai`), every import fails. The fix: create **fake module objects** for each framework module and inject them into `sys.modules` **before** importing the module under test.

### The Problem

```python
# bridge/app/hermes_runner.py
from hermes_ai import AIAgent           # ← ModuleNotFoundError in test venv
from hermes_ai.config import HermesConfig
from dotenv import load_dotenv
```

### The Fixture

```python
@pytest.fixture(autouse=True)
def setup_mocks(monkeypatch, tmp_path):
    import types as pytypes

    # 1. Create a fake hermes_ai module
    hermes_ai = pytypes.ModuleType("hermes_ai")
    hermes_ai.AIAgent = MagicMock()
    monkeypatch.setitem(sys.modules, "hermes_ai", hermes_ai)

    # 2. Create fake submodules (hermes_ai.config, hermes_ai.tool_registry)
    for sub in ["config", "tool_registry"]:
        mod = pytypes.ModuleType(f"hermes_ai.{sub}")
        mod.HermesConfig = MagicMock()
        mod.ToolRegistry = MagicMock()
        monkeypatch.setitem(sys.modules, f"hermes_ai.{sub}", mod)
        setattr(hermes_ai, sub, mod)

    # 3. Mock other missing dependencies
    dotenv = pytypes.ModuleType("dotenv")
    dotenv.load_dotenv = MagicMock()
    monkeypatch.setitem(sys.modules, "dotenv", dotenv)

    # 4. Redirect module-level constants (computed at import time)
    from app import hermes_runner as hr
    monkeypatch.setattr(hr, "_OBSIDIAN", tmp_path / "obsidian")
    monkeypatch.setattr(hr, "_CHANNEL_CONFIG_PATH", tmp_path / "config.yaml")

    return hr
```

### Key Differences from Pattern 1

| Aspect | Pattern 1 (Path Conflict) | Pattern 2 (Missing Framework) |
|--------|---------------------------|-------------------------------|
| Root cause | Local dir shadows venv | Framework not installed |
| Mock strategy | Import real local code, mock only side effects | **Everything** is a fake module |
| Real code tested | Yes — local modules are real | Yes — the module under test is real, all dependencies are mocked |
| Submodule handling | One dummy package, import real modules as attrs | Create each submodule individually |
| Post-import patching | Optional (state file path) | Required (module-level constants computed during import) |

### Common Dependency Chains

For Hermes-dependent modules, you typically need to mock:

```python
DEPS = [
    "hermes_ai",           # AIAgent
    "hermes_ai.config",    # HermesConfig
    "hermes_ai.tool_registry",  # ToolRegistry
    "dotenv",              # load_dotenv
    "dotenv.main",         # load_dotenv (alternate import path)
]
```

Always clear cached imports before re-importing:

```python
for mod in list(sys.modules.keys()):
    if "hermes_runner" in mod or "app.hermes_runner" in mod:
        del sys.modules[mod]
```
