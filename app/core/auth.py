"""
Xác thực (authentication) — JWT token + password hashing.

Module này cung cấp:
  - hash_password / verify_password: sử dụng bcrypt để hash/verify password
  - generate_jwt / decode_jwt / verify_jwt: JWT token cho session
  - create_user_account / login: tạo account và login

Khi user login thành công, trả về JWT token → client lưu vào cookie.
Mỗi request, Flask session kiểm tra cookie có hợp lệ hay không (via middleware).
"""

import os
import uuid
from datetime import datetime, timedelta

import bcrypt
import jwt

from . import storage

# Lấy secret key từ biến môi trường, fallback sang giá trị demo
SECRET_KEY = os.environ.get("SECRET_KEY", "shi-nha-khoa-demo-key")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24


class AuthError(Exception):
    """Lỗi xác thực."""
    pass


class InvalidCredentialsError(AuthError):
    """Username/password sai."""
    pass


class UserAlreadyExistsError(AuthError):
    """User đã tồn tại."""
    pass


def hash_password(password: str) -> str:
    """Hash password bằng bcrypt.

    Args:
        password: plain text password

    Returns:
        bcrypt hash (bytes được decode thành str)
    """
    if not isinstance(password, bytes):
        password = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password, salt)
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password với bcrypt hash.

    Args:
        password: plain text password
        password_hash: bcrypt hash từ DB

    Returns:
        True nếu password đúng
    """
    if not isinstance(password, bytes):
        password = password.encode("utf-8")
    if not isinstance(password_hash, bytes):
        password_hash = password_hash.encode("utf-8")
    return bcrypt.checkpw(password, password_hash)


def generate_jwt(user_id: str, username: str, role: str) -> str:
    """Tạo JWT token cho user.

    Args:
        user_id: ID của user
        username: username
        role: 'admin', 'doctor', hoặc 'guest'

    Returns:
        JWT token (string)
    """
    now = datetime.utcnow()
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(hours=JWT_EXPIRATION_HOURS),
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token


def decode_jwt(token: str) -> dict:
    """Decode JWT token (không verify chữ ký).

    Args:
        token: JWT token

    Returns:
        dict với payload {'sub', 'username', 'role', 'iat', 'exp'}

    Raises:
        jwt.DecodeError: token không hợp lệ
    """
    return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])


def verify_jwt(token: str) -> dict:
    """Verify JWT token (check chữ ký + expiration).

    Args:
        token: JWT token

    Returns:
        dict với payload {'sub', 'username', 'role', 'iat', 'exp'}

    Raises:
        jwt.DecodeError: token không hợp lệ / hết hạn
    """
    try:
        return decode_jwt(token)
    except jwt.ExpiredSignatureError:
        raise AuthError("Token hết hạn")
    except jwt.InvalidTokenError as e:
        raise AuthError(f"Token không hợp lệ: {e}")


def create_user_account(username: str, password: str, role: str, email: str = None, doctor_id: str = None):
    """Tạo user mới và lưu vào DB.

    Args:
        username: username (duy nhất)
        password: plain text password
        role: 'admin', 'doctor', hoặc 'guest'
        email: email (tùy chọn)
        doctor_id: doctor_id (chỉ cho role='doctor')

    Returns:
        dict user info

    Raises:
        UserAlreadyExistsError: username đã tồn tại
        AuthError: lỗi khác
    """
    if storage.get_user_by_username(username):
        raise UserAlreadyExistsError(f"Username '{username}' đã tồn tại")

    user_id = uuid.uuid4().hex
    password_hash = hash_password(password)

    try:
        storage.create_user(
            user_id=user_id,
            username=username,
            password_hash=password_hash,
            role=role,
            email=email,
            doctor_id=doctor_id,
        )
    except storage.DuplicateUsernameError:
        raise UserAlreadyExistsError(f"Username '{username}' đã tồn tại")
    except storage.UserStoreUnavailableError:
        raise  # re-raise nguyên vẹn, không bọc thành AuthError chung chung
    except Exception as e:
        raise AuthError(f"Lỗi tạo user: {e}")

    return {
        "id": user_id,
        "username": username,
        "role": role,
        "email": email,
        "doctor_id": doctor_id,
    }


def login(username: str, password: str) -> dict:
    """Login với username/password.

    Args:
        username: username
        password: plain text password

    Returns:
        dict với {'token', 'user': {...}}

    Raises:
        InvalidCredentialsError: username/password sai
    """
    user = storage.get_user_by_username(username)
    if not user:
        raise InvalidCredentialsError("Username hoặc password sai")

    if not verify_password(password, user["password_hash"]):
        raise InvalidCredentialsError("Username hoặc password sai")

    token = generate_jwt(user["id"], user["username"], user["role"])

    return {
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "email": user.get("email"),
            "doctor_id": user.get("doctor_id"),
        },
    }


def resolve_user_from_token(token: str) -> dict:
    """Đọc token, verify, load user. Trả None nếu bất kỳ bước nào fail
    (không token, token invalid/expired, user không tồn tại, lỗi storage
    bất kỳ kể cả khi chưa cấu hình DB). Không raise — bắt Exception rộng
    có chủ đích, khớp hành vi fail-safe cũ của _check_admin/_get_current_doctor.
    """
    if not token:
        return None
    try:
        payload = verify_jwt(token)
        return storage.get_user_by_id(payload["sub"])
    except Exception:
        return None


def get_user_from_token(token: str) -> dict:
    """Lấy thông tin user từ JWT token (sau khi verify).

    Args:
        token: JWT token

    Returns:
        dict payload từ token

    Raises:
        AuthError: token không hợp lệ / hết hạn
    """
    return verify_jwt(token)
