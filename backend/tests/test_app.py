import os

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")

from types import SimpleNamespace

from routers.projects import validate_project
from services.deployment import snapshot_project
from security import decrypt_secret, encrypt_secret, hash_password, verify_password


def test_password_hash():
    password = "test-password"
    hashed = hash_password(password)
    assert verify_password(password, hashed)
    assert not verify_password("wrong", hashed)


def test_secret_roundtrip():
    value = "secret-value-中文"
    encrypted = encrypt_secret(value)
    assert encrypted.startswith("enc:")
    assert decrypt_secret(encrypted) == value


def _project(cwd):
    return SimpleNamespace(
        name="demo",
        branch="main",
        shell="bash",
        steps=[SimpleNamespace(
            cwd=cwd,
            name="step",
            command="echo ok",
            step_type="command",
            timeout=60,
        )],
        environment=[],
        member_ids=[],
    )


def test_check_rejects_unsafe_cwd():
    try:
        validate_project(_project("/tmp"), None)
        assert False
    except Exception as exc:
        assert "cwd" in str(exc.detail)


def test_check_accepts_home_relative_cwd():
    validate_project(_project("~"), None)


def test_snapshot_contains_project_steps_and_environment():
    project = SimpleNamespace(
        name="demo",
        branch="main",
        shell="bash",
        enabled=True,
        steps=[],
        envs=[],
    )
    snapshot = snapshot_project(project)
    assert '"name": "demo"' in snapshot
    assert '"steps": []' in snapshot
    assert '"environment": []' in snapshot
