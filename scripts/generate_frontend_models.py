"""Generate the frontend response models from the server's OpenAPI schema.

The frontend package deliberately does not depend on the server package, so its
copy of the response models used to be maintained by hand and drifted (see
issue #88). This script regenerates that copy from the schema FastAPI derives
from the server's own models, so the only way the two can disagree is if
somebody forgets to re-run it -- which the `model-codegen` CI job catches by
regenerating and diffing.

Run it from the server package so that the server (and datamodel-code-generator)
are importable::

    cd packages/spectra_inspector_server
    uv run --group codegen python ../../scripts/generate_frontend_models.py

Nothing here is frontend-specific beyond the default output path, so pass
``--output`` to write the models somewhere else.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "packages"
    / "spectra_inspector"
    / "src"
    / "spectra_inspector"
    / "utilities"
    / "model.py"
)

FILE_HEADER = """\
# DO NOT EDIT: generated from the spectra_inspector_server OpenAPI schema.
#
# Regenerate with:
#
#     cd packages/spectra_inspector_server
#     uv run --group codegen python ../../scripts/generate_frontend_models.py
#
# The server's model.py is the source of truth; edits made here are overwritten
# and the model-codegen CI job fails on any difference.
"""


def openapi_schema() -> dict[str, Any]:
    """Build the server's OpenAPI schema without starting a server."""
    from spectra_inspector_server.main import app

    schema: dict[str, Any] = app.openapi()
    return schema


def strip_property_titles(schema: dict[str, Any]) -> dict[str, Any]:
    """Drop the per-property ``title`` FastAPI adds to every field.

    They carry no information for a client -- they are just the field name
    title-cased -- but datamodel-code-generator faithfully turns each one into a
    ``Field(..., title=...)``, which triples the size of the generated file and
    buries the parts of a diff that matter.
    """
    for definition in schema.get("components", {}).get("schemas", {}).values():
        for prop in definition.get("properties", {}).values():
            prop.pop("title", None)
    return schema


def alias_renamed_classes(source: str, schema: dict[str, Any]) -> str:
    """Restore the schema spelling of any class the generator had to rename.

    `MetadataModel` has a field named `Signal` whose type is the `Signal` model,
    and the generator refuses to emit `Signal: Signal` even though it is legal
    under postponed annotations (the server's own models do exactly that). With
    the rename-type strategy it renames the *class* to `Signal_1` and leaves the
    field alone, which is the right trade -- field names are the wire format --
    but it leaves the frontend without a `model.Signal` to import. Aliasing the
    suffixed classes back gives both.
    """
    defined = set(re.findall(r"^class (\w+)\(", source, re.MULTILINE))
    aliases: dict[str, str] = {}
    for name in sorted(schema["components"]["schemas"]):
        if name in defined:
            continue
        renamed = sorted(
            n for n in defined if re.fullmatch(rf"{re.escape(name)}_\d+", n)
        )
        if not renamed:
            msg = f"schema {name!r} produced no class in the generated module"
            raise RuntimeError(msg)
        aliases[name] = renamed[0]

    if not aliases:
        return source

    lines = [
        "",
        "",
        "# These names collide with a field of the same name, so the generator",
        "# suffixed the class. Alias them back to the spelling the server uses.",
        *(f"{name} = {renamed}" for name, renamed in aliases.items()),
        "",
    ]
    return source + "\n".join(lines)


def run_ruff(source: str, filename: Path) -> str:
    """Apply the repo's ruff fixes and formatting to generated source.

    ``--stdin-filename`` is the file the output is *destined* for rather than
    any file on disk: ruff resolves its configuration from that path, so the
    result matches what the ruff pre-commit hooks would do to the checked-in
    file. Without this the hooks would reformat the generated file and the
    codegen CI check would fail on a file nobody edited.
    """
    for args in (["check", "--fix-only"], ["format"]):
        completed = subprocess.run(
            ["ruff", *args, "--quiet", "--stdin-filename", str(filename), "-"],
            input=source,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            msg = f"ruff {args[0]} failed:\n{completed.stderr}"
            raise RuntimeError(msg)
        source = completed.stdout
    return source


def generate_models(schema: dict[str, Any], output: Path) -> str:
    # imported here so that --help works without the codegen group installed
    from datamodel_code_generator import (
        DataModelType,
        FieldTypeCollisionStrategy,
        Formatter,
        InputFileType,
        PythonVersion,
        generate,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / output.name
        generate(
            json.dumps(schema, indent=2),
            input_file_type=InputFileType.OpenAPI,
            input_filename="openapi.json",
            output=target,
            output_model_type=DataModelType.PydanticV2BaseModel,
            target_python_version=PythonVersion.PY_313,
            # keep the schema names verbatim rather than PascalCasing them:
            # the frontend imports `raveledImage`, `directoryListing`, etc.
            custom_class_name_generator=lambda name: name,
            # on a field/class name collision rename the *class*, never the
            # field -- a renamed field would change the JSON keys the models
            # produce and read.
            field_type_collision_strategy=FieldTypeCollisionStrategy.RenameType,
            custom_file_header=FILE_HEADER,
            disable_timestamp=True,
            use_schema_description=True,
            use_standard_collections=True,
            use_union_operator=True,
            use_double_quotes=True,
            formatters=[Formatter.BUILTIN],
        )
        generated = target.read_text(encoding="utf-8")

    return run_ruff(alias_renamed_classes(generated, schema), output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="file to write the generated models to (default: %(default)s)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit non-zero if the file is out of date",
    )
    args = parser.parse_args(argv)

    output: Path = args.output
    generated = generate_models(strip_property_titles(openapi_schema()), output)

    if args.check:
        current = output.read_text(encoding="utf-8") if output.exists() else None
        if current == generated:
            print(f"{output} is up to date")
            return 0
        print(
            f"{output} is out of date, regenerate it with "
            f"`python {Path(__file__).name}`",
            file=sys.stderr,
        )
        return 1

    output.write_text(generated, encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
