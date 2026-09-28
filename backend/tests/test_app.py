from types import SimpleNamespace
from app import check, decrypt_secret, encrypt_secret, hash_password, verify_password

def test_password_hash():
 password="test-password"
 hashed=hash_password(password)
 assert verify_password(password,hashed)
 assert not verify_password("wrong",hashed)

def test_secret_roundtrip():
 value="secret-value-中文"
 encrypted=encrypt_secret(value)
 assert encrypted.startswith("enc:")
 assert decrypt_secret(encrypted)==value

def test_check_rejects_unsafe_cwd():
 x=SimpleNamespace(
  name="demo",branch="main",shell="bash",
  steps=[SimpleNamespace(cwd="/tmp",name="step",command="echo ok")],
  environment=[],
 )
 try:
  check(x)
  assert False
 except Exception as exc:
  assert "cwd" in str(exc.detail)

def test_check_accepts_home_relative_cwd():
 x=SimpleNamespace(
  name="demo",branch="main",shell="bash",
  steps=[SimpleNamespace(cwd="~",name="step",command="echo ok")],
  environment=[],
 )
 check(x)
