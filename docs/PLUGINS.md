# Python lifecycle plugins

Configure trusted importable Python modules in `pd.yaml` or `~/.pd.yaml`:

```yaml
plugins: [my_plugin, my_package.hooks]
```

Use module names, not paths. Modules must be available on the Python import path.
Each module may define any of `before_advance`, `after_advance`,
`before_checkpoint`, `after_checkpoint`, `before_verify`, and `after_verify`.
Each function receives one `PluginContext`: a frozen dataclass with `feature`,
`feature_dir` (a `Path`), `phase` (an integer), `phase_name`, and `state` (a
read-only mapping containing a detached deep copy). Nested values may be changed
locally without affecting PD state or other plugin invocations.

For each event, shell hooks run first in their configured order, followed by
plugins in configuration order. They share the shell hook event timing, including
skipping `before_advance` with `--force`; see [HOOKS.md](HOOKS.md). Each plugin
gets its own snapshot. Plugins load once per configuration instance. Invalid
configuration, import failures, and non-callable hooks raise `ConfigError`;
exceptions during hook execution print a warning and do not block the operation.

Plugins execute arbitrary Python code with your user privileges, including at
import time. Only configure trusted modules. Python hooks have no timeout or
sandbox and do not replace gates.
