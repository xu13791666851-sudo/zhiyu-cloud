#!/usr/bin/env python3
"""Patch gradio_client to handle bool schemas (additionalProperties: true)."""
import importlib.util

spec = importlib.util.find_spec("gradio_client")
if not spec or not spec.origin:
    print("gradio_client not found")
    exit(0)

pkg_dir = spec.origin.replace("__init__.py", "")
utils_file = pkg_dir + "utils.py"

with open(utils_file, "r", encoding="utf-8") as f:
    code = f.read()

# Patch get_type: handle bool schema
old = 'def get_type(schema: dict):\n    if "const" in schema:'
new = 'def get_type(schema: dict):\n    if isinstance(schema, bool):\n        return "boolean"\n    if isinstance(schema, dict) and "const" in schema:'
code = code.replace(old, new)
print("Patched get_type()" if old not in code else "get_type() already patched")

# Patch _json_schema_to_python_type: handle bool schema at entry
old = "if schema == {}:\n        return \"Any\"\n    type_ = get_type(schema)"
new = "if isinstance(schema, bool):\n        return \"bool\"\n    if schema == {}:\n        return \"Any\"\n    type_ = get_type(schema)"
code = code.replace(old, new)
print("Patched _json_schema_to_python_type()" if old not in code else "_json_schema_to_python_type() already patched")

with open(utils_file, "w", encoding="utf-8") as f:
    f.write(code)

print(f"Done: {utils_file}")
