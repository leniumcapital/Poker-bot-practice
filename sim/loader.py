"""Load a bot version from any directory under its own module name.

Each version gets its own copy of every bot module, so config overrides on one
version cannot leak into another. This is what makes A/B testing two code trees
or two configs in one process safe.
"""
import hashlib
import importlib
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CACHE = {}


def apply_overrides(cfg, overrides):
    """Keys may be dotted to reach into dicts: 'OPEN_PCT.2': 0.5."""
    for key, value in (overrides or {}).items():
        parts = key.split(".")
        if len(parts) == 1:
            setattr(cfg, key, value)
            continue
        node = getattr(cfg, parts[0])
        for p in parts[1:-1]:
            node = node[_coerce(node, p)]
        node[_coerce(node, parts[-1])] = value


def _coerce(node, part):
    if isinstance(node, list) or (isinstance(node, dict) and part not in node and part.lstrip("-").isdigit()):
        return int(part)
    return part


def load_agent_class(path=None, overrides=None):
    path = os.path.abspath(path or os.path.join(ROOT, "bot"))
    tag = hashlib.md5((path + json.dumps(overrides or {}, sort_keys=True)).encode()).hexdigest()[:10]
    if tag in _CACHE:
        return _CACHE[tag]
    alias = "botv_" + tag
    spec = importlib.util.spec_from_file_location(
        alias, os.path.join(path, "__init__.py"), submodule_search_locations=[path])
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    cfg = importlib.import_module(alias + ".config")
    apply_overrides(cfg, overrides)
    agent_mod = importlib.import_module(alias + ".agent")
    _CACHE[tag] = agent_mod.Agent
    return agent_mod.Agent
