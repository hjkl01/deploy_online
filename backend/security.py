import base64,hashlib
import bcrypt
from cryptography.fernet import Fernet,InvalidToken
from config import settings

FERNET=Fernet(base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest()))

def encrypt_secret(value:str)->str:
 return "enc:"+FERNET.encrypt(value.encode()).decode()

def decrypt_secret(value:str)->str:
 if not value.startswith("enc:"):return value
 try:return FERNET.decrypt(value[4:].encode()).decode()
 except InvalidToken:raise RuntimeError("无法解密环境变量，请检查 SECRET_KEY")

def hash_password(password:str):
 if len(password.encode())>72:raise RuntimeError("ADMIN_PASSWORD 不能超过 72 字节")
 return bcrypt.hashpw(password.encode(),bcrypt.gensalt()).decode()

def verify_password(password:str,password_hash:str):
 try:return bcrypt.checkpw(password.encode(),password_hash.encode())
 except (ValueError,TypeError):return False
