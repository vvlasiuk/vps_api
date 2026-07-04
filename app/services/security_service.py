import bcrypt as bcrypt_lib


def hash_password(password: str) -> str:
    return bcrypt_lib.hashpw(password.encode(), bcrypt_lib.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt_lib.checkpw(password.encode(), hashed.encode())
