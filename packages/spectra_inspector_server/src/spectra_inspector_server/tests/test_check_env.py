"""``scripts/check_env.py``, and the ``defaults.env`` templates checked with it.

The script reads both packages' ``settings.py`` with ``ast``, so these tests
run against the real settings of the frontend as well without importing it.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from spectra_inspector_server.settings import ENV_PREFIX, Settings

REPO_ROOT = Path(__file__).resolve().parents[5]
SCRIPT = REPO_ROOT / "scripts" / "check_env.py"


@pytest.fixture(scope="module")
def check_env() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_env", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve the script's deferred annotations through sys.modules
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _findings(
    check_env: ModuleType, tmp_path: Path, text: str, package_index: int = 0
) -> dict[str, tuple[str, str]]:
    package = check_env.PACKAGES[package_index]
    other = check_env.PACKAGES[1 - package_index]
    path = tmp_path / ".env"
    path.write_text(text)
    report = check_env.check_env_file(
        check_env.parse_env_file(path),
        check_env.read_known_settings(package.settings_path),
        check_env.read_known_settings(other.settings_path),
        other.label,
    )
    return {f.key: (f.level, f.action) for f in report.findings}


def test_known_settings_match_the_model(check_env: ModuleType) -> None:
    known = check_env.read_known_settings(check_env.PACKAGES[0].settings_path)
    assert known.prefix == ENV_PREFIX
    assert set(known.defaults) == set(Settings.model_fields)
    assert (
        known.defaults["max_queued_ops"]
        == Settings.model_fields["max_queued_ops"].default
    )


def test_key_problems_are_classified(check_env: ModuleType, tmp_path: Path) -> None:
    findings = _findings(
        check_env,
        tmp_path,
        "SPECTRA_INSPECTOR_DATA_ROOT='/data'  # fine\n"
        "export SPECTRA_INSPECTOR_LOG_LEVEL=INFO\n"
        "SPECTRA_INSPECTOR_MAX_QUEUE_OPS=4\n"
        "SPECTRA_INSPECTOR_LONG_GONE=1\n"
        "SPECTRA_INSPECTOR_WRITE_DIR=/tmp\n"
        "HOST_DATA_ROOT=/host\n"
        "SOMETHING_ELSE=1\n"
        "SPECTRA_INSPECTOR_DESKTOP_MODE=false\n"
        "SPECTRA_INSPECTOR_DESKTOP_MODE=true\n"
        "# SPECTRA_INSPECTOR_MAX_DATASETS=500\n",
    )
    assert "SPECTRA_INSPECTOR_DATA_ROOT" not in findings
    assert "SPECTRA_INSPECTOR_LOG_LEVEL" not in findings
    assert findings["SPECTRA_INSPECTOR_MAX_QUEUE_OPS"] == ("error", "RENAME")
    assert findings["SPECTRA_INSPECTOR_LONG_GONE"] == ("error", "REMOVE")
    assert findings["SPECTRA_INSPECTOR_WRITE_DIR"] == ("error", "MOVE")
    assert findings["HOST_DATA_ROOT"] == ("error", "RENAME")
    assert findings["SOMETHING_ELSE"] == ("warning", "IGNORED")
    assert findings["SPECTRA_INSPECTOR_DESKTOP_MODE"] == ("warning", "DUPLICATE")
    assert findings["SPECTRA_INSPECTOR_MAX_DATASETS"] == ("info", "unset")
    assert findings["SPECTRA_INSPECTOR_MAX_QUEUED_OPS"] == ("info", "unset")


@pytest.mark.parametrize(
    ("server", "frontend", "mismatch"),
    [
        ("SPECTRA_INSPECTOR_DESKTOP_MODE=true", "", True),
        ("", "SPECTRA_INSPECTOR_DESKTOP_MODE = 1", True),
        (
            "SPECTRA_INSPECTOR_DESKTOP_MODE=True",
            "SPECTRA_INSPECTOR_DESKTOP_MODE=yes",
            False,
        ),
        ("SPECTRA_INSPECTOR_DESKTOP_MODE=false", "", False),
        ("", "", False),
    ],
)
def test_desktop_mode_must_match(
    check_env: ModuleType,
    tmp_path: Path,
    server: str,
    frontend: str,
    mismatch: bool,
) -> None:
    checked = []
    for package, text in zip(check_env.PACKAGES, (server, frontend), strict=True):
        path = tmp_path / f"{package.label}.env"
        path.write_text(text)
        checked.append(
            (
                package,
                check_env.parse_env_file(path),
                check_env.read_known_settings(package.settings_path),
            )
        )
    problems = check_env.check_must_match(checked)
    assert bool(problems) is mismatch
    if mismatch:
        assert "SPECTRA_INSPECTOR_DESKTOP_MODE" in problems[0]


def test_compose_overrides_are_attributed_to_the_frontend(
    check_env: ModuleType,
) -> None:
    overrides = check_env.compose_overrides(check_env.COMPOSE_FILE, ".env")
    frontend_env = check_env.PACKAGES[1].directory / ".env"
    assert overrides == {
        frontend_env.resolve(): {
            "SPECTRA_INSPECTOR_SERVER_HOST": "fastapi",
            "SPECTRA_INSPECTOR_SERVER_PORT": "8000",
            "SPECTRA_INSPECTOR_WRITE_DIR": "/tmp/spectra_inspector_writes",
        }
    }


def test_resolve_precedence(check_env: ModuleType, tmp_path: Path) -> None:
    frontend = check_env.PACKAGES[1]
    known = check_env.read_known_settings(frontend.settings_path)
    path = tmp_path / ".env"
    path.write_text(
        "SPECTRA_INSPECTOR_SERVER_HOST=localhost\n"
        "SPECTRA_INSPECTOR_MAX_TMP_DIRS=7\n"
        "SPECTRA_INSPECTOR_N_FRONTEND_WORKERS=3\n"
    )
    env = check_env.parse_env_file(path)

    docker = {
        key: (value, source)
        for key, value, source in check_env.resolve(
            env,
            known,
            ("compose.yaml", {"SPECTRA_INSPECTOR_SERVER_HOST": "fastapi"}),
            (
                "Dockerfile",
                {
                    "SPECTRA_INSPECTOR_N_FRONTEND_WORKERS": "2",
                    "SPECTRA_INSPECTOR_SERVER_PORT": "9000",
                },
            ),
        )
    }
    assert docker["SPECTRA_INSPECTOR_SERVER_HOST"] == (
        "fastapi",
        "compose.yaml (the .env has localhost)",
    )
    assert docker["SPECTRA_INSPECTOR_MAX_TMP_DIRS"] == ("7", ".env")
    assert docker["SPECTRA_INSPECTOR_N_FRONTEND_WORKERS"] == ("3", ".env")
    assert docker["SPECTRA_INSPECTOR_SERVER_PORT"] == ("9000", "Dockerfile")
    assert docker["SPECTRA_INSPECTOR_DESKTOP_MODE"] == ("False", "default")

    native = {
        key: (value, source)
        for key, value, source in check_env.resolve(
            env, known, ("exported", {"SPECTRA_INSPECTOR_SERVER_PORT": "8001"})
        )
    }
    assert native["SPECTRA_INSPECTOR_SERVER_HOST"] == ("localhost", ".env")
    assert native["SPECTRA_INSPECTOR_SERVER_PORT"] == ("8001", "exported")
    assert native["SPECTRA_INSPECTOR_N_FRONTEND_WORKERS"] == ("3", ".env")


def test_dockerfile_env_is_read(check_env: ModuleType) -> None:
    for package, key in zip(
        check_env.PACKAGES,
        ("SPECTRA_INSPECTOR_N_FASTAPI_WORKERS", "SPECTRA_INSPECTOR_N_FRONTEND_WORKERS"),
        strict=True,
    ):
        assert key in check_env.dockerfile_env(package.directory / "Dockerfile")


@pytest.mark.parametrize("package_index", [0, 1])
def test_defaults_env_covers_every_setting(
    check_env: ModuleType, tmp_path: Path, package_index: int
) -> None:
    package = check_env.PACKAGES[package_index]
    template = package.directory / "defaults.env"
    findings = _findings(check_env, tmp_path, template.read_text(), package_index)
    assert not {k: v for k, v in findings.items() if v[0] != "info"}

    commented = check_env.parse_env_file(template).commented
    undocumented = [
        key
        for key, (_, action) in findings.items()
        if action == "unset" and key not in commented
    ]
    assert not undocumented


def test_directory_settings_exist(check_env: ModuleType) -> None:
    for package in check_env.PACKAGES:
        known = check_env.read_known_settings(package.settings_path)
        assert set(check_env.DIRECTORY_SETTINGS[package.label]) <= set(known.defaults)


def test_directories_must_exist(check_env: ModuleType, tmp_path: Path) -> None:
    known = check_env.read_known_settings(check_env.PACKAGES[0].settings_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "a_file").write_text("")
    path = tmp_path / ".env"

    def problems(text: str, names: list[str]) -> dict[str, str]:
        path.write_text(text)
        resolved = check_env.resolve(
            check_env.parse_env_file(path), known, ("exported", {})
        )
        found = check_env.check_directories(
            resolved, known, names, tmp_path, mode="docker", level="error"
        )
        assert all((f.level, f.action) == ("error", "NOT FOUND") for f in found)
        return {f.key: f.detail for f in found}

    names = ["host_data_root", "derived_data_dir"]
    assert not problems(
        f"SPECTRA_INSPECTOR_HOST_DATA_ROOT='{tmp_path / 'data'}'\n"
        "SPECTRA_INSPECTOR_DATA_ROOT=/only/in/the/container\n",
        names,
    )
    assert not problems("SPECTRA_INSPECTOR_HOST_DATA_ROOT=data\n", names)
    assert not problems("", names)
    assert problems(
        "SPECTRA_INSPECTOR_HOST_DATA_ROOT=/no/such/tree\n"
        "SPECTRA_INSPECTOR_DERIVED_DATA_DIR=a_file\n",
        names,
    ) == {
        "SPECTRA_INSPECTOR_HOST_DATA_ROOT": "docker: no /no/such/tree here",
        "SPECTRA_INSPECTOR_DERIVED_DATA_DIR": "docker: a_file is not a directory",
    }


def test_created_on_use_directory_needs_its_parent(
    check_env: ModuleType, tmp_path: Path
) -> None:
    known = check_env.read_known_settings(check_env.PACKAGES[1].settings_path)
    path = tmp_path / ".env"

    def problems(write_dir: str) -> list[str]:
        path.write_text(f"SPECTRA_INSPECTOR_WRITE_DIR={write_dir}\n")
        resolved = check_env.resolve(
            check_env.parse_env_file(path), known, ("exported", {})
        )
        return [
            f.key
            for f in check_env.check_directories(
                resolved, known, ["write_dir"], tmp_path, mode="native", level="error"
            )
        ]

    assert not problems("not_made_yet")
    assert problems("no_parent/not_made_yet") == ["SPECTRA_INSPECTOR_WRITE_DIR"]


@pytest.fixture
def packages(
    check_env: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> list[Any]:
    """Copies of both packages' settings under tmp_path, each with a ``.env``."""
    copies = []
    for package in check_env.PACKAGES:
        directory = tmp_path / package.label
        settings_dir = directory / "src" / package.module
        settings_dir.mkdir(parents=True)
        (settings_dir / "settings.py").write_text(package.settings_path.read_text())
        (directory / ".env").write_text("SPECTRA_INSPECTOR_DESKTOP_MODE=false\n")
        copies.append(check_env.Package(package.label, directory, package.module))
    monkeypatch.setattr(check_env, "PACKAGES", tuple(copies))
    return copies


def test_missing_directory_is_an_error_only_for_its_mode(
    check_env: ModuleType,
    packages: list[Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    (packages[0].directory / ".env").write_text(
        "SPECTRA_INSPECTOR_HOST_DATA_ROOT=/no/such/tree\n"
    )
    assert check_env.main([]) == 0
    assert "NOT FOUND" in capsys.readouterr().out
    assert check_env.main(["--mode", "native"]) == 0
    assert "NOT FOUND" not in capsys.readouterr().out
    assert check_env.main(["--mode", "docker"]) == 1
    assert "docker: no /no/such/tree here" in capsys.readouterr().out


def test_resolved_lists_each_mode(
    check_env: ModuleType,
    packages: list[Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("SPECTRA_INSPECTOR_LOG_LEVEL", "DEBUG")
    assert check_env.main(["--resolved"]) == 0
    out = capsys.readouterr().out
    for package in packages:
        assert f"{package.label} settings, docker" in out
        assert f"{package.label} settings, native" in out
    assert out.count("DEBUG") == 1
    assert check_env.main(["--resolved", "--mode", "docker"]) == 0
    assert "native" not in capsys.readouterr().out


def test_main_exit_status(
    check_env: ModuleType,
    packages: list[Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert check_env.main([]) == 0
    assert "nothing to fix" in capsys.readouterr().out

    (packages[0].directory / ".env").write_text("SPECTRA_INSPECTOR_DESKTOP_MODE=true\n")
    assert check_env.main([]) == 1
    assert "MISMATCH" in capsys.readouterr().out

    (packages[1].directory / ".env").unlink()
    assert check_env.main(["-q"]) == 1
    assert "MISSING" in capsys.readouterr().out
