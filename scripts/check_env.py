"""Check both packages' ``.env`` files against the settings the code reads.

Under docker the ``.env`` files reach the containers as environment variables,
and pydantic-settings ignores an environment variable it has no field for. A
stale or misspelled key therefore does nothing at all, and the setting it was
meant for quietly runs on its default. This script reports those keys, the
settings each ``.env`` leaves on their defaults, settings that have to agree
between the two packages but do not, and host directories that do not exist.

The known settings are read from each package's ``settings.py`` with ``ast``
rather than by importing it, so the script needs nothing beyond a bare Python
and always describes the checked-out code. It checks key names only: a value
the settings model rejects already stops the container at startup.

Run it from anywhere, after updating the code and before restarting::

    python3 scripts/check_env.py

``--resolved`` also prints the value every setting ends up with in the
containers. It never edits a file. The exit status is 1 when something has to be fixed.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = REPO_ROOT / "compose.yaml"

ERROR = "error"
WARNING = "warning"
INFO = "info"

# settings both packages declare whose values have to agree for the app to work
MUST_MATCH = ("desktop_mode",)

# settings, by package label, that name a directory on the host when the app
# runs under docker. The server's data_root is a path inside the container and
# compose replaces the frontend's write_dir, so neither can be checked here.
HOST_DIRECTORIES = {"server": ("host_data_root", "derived_data_dir")}

_TRUE = {"1", "true", "t", "yes", "y", "on"}
_FALSE = {"0", "false", "f", "no", "n", "off"}

_ASSIGNMENT = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
_COMPOSE_SERVICE = re.compile(r"^  (\w[\w-]*):\s*$")
_COMPOSE_ENV_FILE = re.compile(r"^\s+env_file:\s*(\S+)\s*$")
_COMPOSE_ENV_ENTRY = re.compile(r"^\s+- ([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
_DOCKERFILE_ENV = re.compile(r"^ENV\s+([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


@dataclass(frozen=True)
class Package:
    label: str
    directory: Path
    module: str

    @property
    def settings_path(self) -> Path:
        return self.directory / "src" / self.module / "settings.py"


PACKAGES = (
    Package(
        "server",
        REPO_ROOT / "packages" / "spectra_inspector_server",
        "spectra_inspector_server",
    ),
    Package(
        "frontend",
        REPO_ROOT / "packages" / "spectra_inspector",
        "spectra_inspector",
    ),
)


@dataclass(frozen=True)
class KnownSettings:
    prefix: str
    # field name -> default, as a Python value where the source has a literal
    defaults: dict[str, Any]


@dataclass(frozen=True)
class EnvFile:
    path: Path
    # (key, value) for every assignment, in file order
    entries: list[tuple[str, str]]
    # keys that only appear in a commented-out assignment
    commented: set[str]

    def value_of(self, env_key: str) -> str | None:
        """Value of the last assignment to ``env_key``, compared without case."""
        found = None
        for key, value in self.entries:
            if key.upper() == env_key.upper():
                found = value
        return found


@dataclass(frozen=True)
class Finding:
    level: str
    action: str
    key: str
    detail: str = ""


@dataclass
class Report:
    path: Path
    n_keys: int = 0
    findings: list[Finding] = field(default_factory=list)

    def add(self, level: str, action: str, key: str, detail: str = "") -> None:
        self.findings.append(Finding(level, action, key, detail))

    @property
    def n_errors(self) -> int:
        return sum(finding.level == ERROR for finding in self.findings)


def read_known_settings(settings_path: Path) -> KnownSettings:
    """Read the env prefix and the ``Settings`` fields from a settings module."""
    tree = ast.parse(settings_path.read_text(encoding="utf-8"))
    prefix = ""
    defaults: dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "ENV_PREFIX"
            for target in node.targets
        ):
            prefix = ast.literal_eval(node.value)
        if isinstance(node, ast.ClassDef) and node.name == "Settings":
            for statement in node.body:
                if isinstance(statement, ast.AnnAssign) and isinstance(
                    statement.target, ast.Name
                ):
                    defaults[statement.target.id] = _default_of(statement)
    if not prefix or not defaults:
        msg = f"could not find ENV_PREFIX and the Settings fields in {settings_path}"
        raise ValueError(msg)
    return KnownSettings(prefix, defaults)


def _default_of(statement: ast.AnnAssign) -> Any:
    if statement.value is None:
        return "required"
    try:
        return ast.literal_eval(statement.value)
    except ValueError:
        return ast.unparse(statement.value)


def _strip_value(raw: str) -> str:
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        closing = raw.find(raw[0], 1)
        if closing != -1:
            return raw[1:closing]
    return raw.split(" #", 1)[0].strip()


def parse_env_file(path: Path) -> EnvFile:
    entries: list[tuple[str, str]] = []
    commented: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            match = _ASSIGNMENT.match(stripped.lstrip("#").strip())
            if match:
                commented.add(match.group(1))
            continue
        match = _ASSIGNMENT.match(stripped)
        if match:
            entries.append((match.group(1), _strip_value(match.group(2))))
    commented -= {key for key, _ in entries}
    return EnvFile(path, entries, commented)


def compose_overrides(compose_file: Path, env_name: str) -> dict[Path, dict[str, str]]:
    """Variables each service's ``environment`` sets, keyed by its env_file.

    Those win over the env_file inside the container, so the same key in the
    ``.env`` only matters when running outside docker.
    """
    if not compose_file.is_file():
        return {}
    overrides: dict[Path, dict[str, str]] = {}
    env_file: Path | None = None
    pending: dict[str, str] = {}
    for line in compose_file.read_text(encoding="utf-8").splitlines():
        if _COMPOSE_SERVICE.match(line) or (line and not line.startswith(" ")):
            if env_file is not None and pending:
                overrides.setdefault(env_file, {}).update(pending)
            env_file, pending = None, {}
            continue
        match = _COMPOSE_ENV_FILE.match(line)
        if match:
            declared = (compose_file.parent / match.group(1)).resolve()
            env_file = declared.with_name(env_name)
            continue
        match = _COMPOSE_ENV_ENTRY.match(line)
        if match:
            pending[match.group(1)] = _strip_value(match.group(2))
    if env_file is not None and pending:
        overrides.setdefault(env_file, {}).update(pending)
    return overrides


def dockerfile_env(dockerfile: Path) -> dict[str, str]:
    """Variables the image sets with ``ENV``, which a ``.env`` entry overrides."""
    if not dockerfile.is_file():
        return {}
    found = {}
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
        match = _DOCKERFILE_ENV.match(line)
        if match:
            found[match.group(1)] = _strip_value(match.group(2))
    return found


def resolve(
    env: EnvFile,
    known: KnownSettings,
    overridden: dict[str, str],
    image_env: dict[str, str],
) -> list[tuple[str, str, str]]:
    """Each setting's value in the container and where it comes from.

    The order of precedence is compose's ``environment``, the ``.env``, the
    image's ``ENV`` and then the default in ``settings.py``. Values are the
    text the settings model is given, not what it parses them into.
    """
    resolved = []
    for name, default in known.defaults.items():
        env_key = f"{known.prefix}{name.upper()}"
        in_env = env.value_of(env_key)
        if env_key in overridden:
            source = "compose.yaml"
            if in_env is not None:
                source += f" (outside docker: {in_env})"
            resolved.append((env_key, overridden[env_key], source))
        elif in_env is not None:
            resolved.append((env_key, in_env, env.path.name))
        elif env_key in image_env:
            resolved.append((env_key, image_env[env_key], "Dockerfile"))
        else:
            resolved.append((env_key, str(default), "default"))
    return resolved


def check_env_file(
    env: EnvFile,
    known: KnownSettings,
    other: KnownSettings,
    other_label: str,
    overridden: dict[str, str] | None = None,
) -> Report:
    """Compare one ``.env`` with its package's settings.

    ``other`` is the other package's settings, used to recognise a key that
    was put in the wrong file.
    """
    report = Report(env.path, n_keys=len(env.entries))
    prefix = known.prefix
    env_keys = {f"{prefix}{name.upper()}": name for name in known.defaults}
    other_keys = {f"{other.prefix}{name.upper()}" for name in other.defaults}
    overridden = overridden or {}

    seen: set[str] = set()
    for key, _ in env.entries:
        upper = key.upper()
        if upper in seen:
            report.add(WARNING, "DUPLICATE", key, "set more than once, the last wins")
            continue
        seen.add(upper)

        if upper in env_keys:
            if key != upper:
                # compose interpolation and the Dockerfile CMD match exactly
                report.add(WARNING, "RENAME", key, f"spell it {upper}")
            elif key in overridden:
                report.add(INFO, "note", key, "compose.yaml overrides this in docker")
        elif key.lower() in known.defaults:
            report.add(ERROR, "RENAME", key, f"needs the prefix: {prefix}{upper}")
        elif not upper.startswith(prefix.upper()):
            report.add(WARNING, "IGNORED", key, f"no {prefix} prefix, never read")
        elif upper in other_keys:
            report.add(ERROR, "MOVE", key, f"a {other_label} setting, not read here")
        else:
            close = difflib.get_close_matches(upper, env_keys, n=1, cutoff=0.8)
            if close and close[0] not in seen:
                report.add(ERROR, "RENAME", key, f"did you mean {close[0]}?")
            else:
                report.add(ERROR, "REMOVE", key, "not a setting")

    for env_key, name in env_keys.items():
        if env_key not in seen:
            note = f"default: {known.defaults[name]!r}"
            if env_key in env.commented:
                note += ", commented out"
            report.add(INFO, "unset", env_key, note)
    return report


def check_host_directories(
    env: EnvFile, known: KnownSettings, names: tuple[str, ...], base: Path
) -> list[Finding]:
    """The settings in ``names`` that the file sets to a missing directory.

    A relative path is taken from ``base``, as compose takes it from the
    directory of the compose file. A setting the file leaves out is skipped.
    """
    findings = []
    for name in names:
        env_key = f"{known.prefix}{name.upper()}"
        value = env.value_of(env_key)
        if not value:
            continue
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = base / path
        if not path.exists():
            findings.append(Finding(ERROR, "NOT FOUND", env_key, f"no {value} here"))
        elif not path.is_dir():
            findings.append(Finding(ERROR, "NOT FOUND", env_key, f"{value} is a file"))
    return findings


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return None


def _effective(env: EnvFile, known: KnownSettings, name: str) -> Any:
    raw = env.value_of(f"{known.prefix}{name.upper()}")
    return known.defaults[name] if raw is None else raw


def check_must_match(
    checked: list[tuple[Package, EnvFile, KnownSettings]],
) -> list[str]:
    """Settings in ``MUST_MATCH`` whose effective values differ between files."""
    problems = []
    for name in MUST_MATCH:
        holders = [item for item in checked if name in item[2].defaults]
        values = [_effective(env, known, name) for _, env, known in holders]
        normalized = [_as_bool(value) for value in values]
        comparable = values if None in normalized else normalized
        if len(set(map(str, comparable))) > 1:
            sides = ", ".join(
                f"{package.label} {value!s}"
                + (
                    ""
                    if env.value_of(f"{known.prefix}{name.upper()}")
                    else " (default)"
                )
                for (package, env, known), value in zip(holders, values)
            )
            key = f"{holders[0][2].prefix}{name.upper()}"
            problems.append(f"{key} has to be the same in both files: {sides}")
    return problems


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _print_report(report: Report, *, quiet: bool) -> None:
    print(_display(report.path))
    shown = [f for f in report.findings if not (quiet and f.level == INFO)]
    if not report.n_errors:
        print(f"  ok        {report.n_keys} keys")
    width = max((len(finding.key) for finding in shown), default=0)
    for finding in shown:
        print(f"  {finding.action:<9} {finding.key:<{width}}  {finding.detail}")
    print()


def _print_resolved(label: str, resolved: list[tuple[str, str, str]]) -> None:
    print(f"{label} settings in docker")
    key_width = max(len(key) for key, _, _ in resolved)
    value_width = max(len(value) for _, value, _ in resolved)
    for key, value, source in resolved:
        print(f"  {key:<{key_width}}  {value:<{value_width}}  {source}")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    parser.add_argument(
        "--env-name",
        default=".env",
        help="file to check in each package directory (default: .env)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="leave out the settings that are on their defaults",
    )
    parser.add_argument(
        "--resolved",
        action="store_true",
        help="also print the value every setting ends up with in the "
        "containers and where it comes from",
    )
    args = parser.parse_args(argv)

    settings = {
        package: read_known_settings(package.settings_path) for package in PACKAGES
    }
    overrides = compose_overrides(COMPOSE_FILE, args.env_name)

    n_problems = 0
    checked: list[tuple[Package, EnvFile, KnownSettings]] = []
    for package in PACKAGES:
        path = package.directory / args.env_name
        if not path.is_file():
            print(_display(path))
            print("  MISSING   copy the defaults.env next to it and edit\n")
            n_problems += 1
            continue
        other = next(p for p in PACKAGES if p is not package)
        env = parse_env_file(path)
        report = check_env_file(
            env,
            settings[package],
            settings[other],
            other.label,
            overrides.get(path.resolve()),
        )
        report.findings.extend(
            check_host_directories(
                env,
                settings[package],
                HOST_DIRECTORIES.get(package.label, ()),
                REPO_ROOT,
            )
        )
        _print_report(report, quiet=args.quiet or args.resolved)
        if args.resolved:
            _print_resolved(
                package.label,
                resolve(
                    env,
                    settings[package],
                    overrides.get(path.resolve(), {}),
                    dockerfile_env(package.directory / "Dockerfile"),
                ),
            )
        n_problems += report.n_errors
        checked.append((package, env, settings[package]))

    for problem in check_must_match(checked):
        print(f"MISMATCH  {problem}")
        n_problems += 1

    if n_problems:
        print(f"{n_problems} problem{'s' if n_problems != 1 else ''} to fix")
        return 1
    print("nothing to fix")
    return 0


if __name__ == "__main__":
    sys.exit(main())
