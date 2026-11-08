import subprocess
import sys

import pytest

from tools.public_beta_restic_guard import (
    ResticGuardError,
    main,
    load_public_beta_restic_env,
    verify_public_beta_repository,
)


def _write_env(path, text: str):
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)


def test_public_beta_restic_env_requires_explicit_repo_id(tmp_path):
    env_file = tmp_path / "restic.env"
    _write_env(
        env_file,
        "\n".join(
            [
                "RESTIC_REPOSITORY=b2:bucket:/public-beta",
                "RESTIC_PASSWORD=synthetic",
            ]
        )
        + "\n",
    )
    with pytest.raises(ResticGuardError, match="missing_public_beta_repository_id"):
        load_public_beta_restic_env(env_file)


def test_public_beta_repository_id_mismatch_is_refused(monkeypatch, tmp_path):
    env_file = tmp_path / "restic.env"
    expected = "a" * 64
    actual = "b" * 64
    _write_env(
        env_file,
        "\n".join(
            [
                "RESTIC_REPOSITORY=b2:bucket:/public-beta",
                "RESTIC_PASSWORD=synthetic",
                f"DOCUMIND_PUBLIC_BETA_RESTIC_REPO_ID={expected}",
            ]
        )
        + "\n",
    )

    env, expected_repo_id = load_public_beta_restic_env(env_file)
    assert expected_repo_id == expected

    def fake_run(argv, env=None, capture_output=False, text=False, timeout=None, check=False):
        return subprocess.CompletedProcess(argv, 0, stdout=f"{{\"id\":\"{actual}\"}}", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ResticGuardError, match="repository_id_mismatch"):
        verify_public_beta_repository(env, expected_repo_id)


def test_public_beta_repository_id_match_is_accepted(monkeypatch, tmp_path):
    env_file = tmp_path / "restic.env"
    expected = "c" * 64
    _write_env(
        env_file,
        "\n".join(
            [
                "RESTIC_REPOSITORY=b2:bucket:/public-beta",
                "RESTIC_PASSWORD=synthetic",
                f"DOCUMIND_PUBLIC_BETA_RESTIC_REPO_ID={expected}",
            ]
        )
        + "\n",
    )

    env, expected_repo_id = load_public_beta_restic_env(env_file)

    def fake_run(argv, env=None, capture_output=False, text=False, timeout=None, check=False):
        return subprocess.CompletedProcess(argv, 0, stdout=f"{{\"id\":\"{expected}\"}}", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    verify_public_beta_repository(env, expected_repo_id)


def test_public_beta_repository_id_can_be_discovered_without_expected_id(monkeypatch, tmp_path, capsys):
    """Discovery mode is used to record DOCUMIND_PUBLIC_BETA_RESTIC_REPO_ID safely."""

    env_file = tmp_path / "restic.env"
    discovered = "d" * 64
    _write_env(
        env_file,
        "\n".join(
            [
                "RESTIC_REPOSITORY=b2:bucket:/public-beta",
                "RESTIC_PASSWORD=synthetic",
            ]
        )
        + "\n",
    )

    def fake_run(argv, env=None, capture_output=False, text=False, timeout=None, check=False):
        assert argv[:3] == ["restic", "cat", "config"]
        return subprocess.CompletedProcess(argv, 0, stdout=f"{{\"id\":\"{discovered}\"}}", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        ["public_beta_restic_guard", "--env-file", str(env_file), "--discover-repo-id"],
    )

    main()
    captured = capsys.readouterr()
    assert captured.out.strip() == discovered


def test_public_beta_repository_id_can_be_recorded(monkeypatch, tmp_path, capsys):
    env_file = tmp_path / "restic.env"
    discovered = "e" * 64
    password = tmp_path / 'password'
    password.write_text('synthetic', encoding='utf-8')
    password.chmod(0o600)
    _write_env(
        env_file,
        "\n".join(
            [
                "RESTIC_REPOSITORY=b2:bucket:/public-beta",
                f"RESTIC_PASSWORD_FILE='{password.as_posix()}'",
                "B2_ACCOUNT_ID=synthetic-id",
                "B2_ACCOUNT_KEY=synthetic-key",
            ]
        )
        + "\n",
    )

    def fake_run(argv, env=None, capture_output=False, text=False, timeout=None, check=False):
        assert argv[:3] == ["restic", "cat", "config"]
        return subprocess.CompletedProcess(argv, 0, stdout=f"{{\"id\":\"{discovered}\"}}", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        ["public_beta_restic_guard", "--env-file", str(env_file), "--record-repo-id",
         "--expected-bucket", "bucket", "--expected-prefix", "/public-beta"],
    )

    main()
    captured = capsys.readouterr()
    assert "recorded" in captured.out.lower()
    assert discovered not in captured.out
    assert f"DOCUMIND_PUBLIC_BETA_RESTIC_REPO_ID={discovered}" in env_file.read_text(encoding="utf-8")
