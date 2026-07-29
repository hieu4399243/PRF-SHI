"""
Test Authentication System — demo cách sử dụng JWT auth.

Chạy:
    python tests/test_auth_demo.py
"""

import json
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import auth


def test_password_hashing():
    """Test bcrypt password hashing."""
    print("\n🔒 Test Password Hashing")
    password = "my-secure-password123"
    
    # Hash password
    hashed = auth.hash_password(password)
    print(f"  Original: {password}")
    print(f"  Hashed: {hashed[:50]}...")
    
    # Verify correct password
    assert auth.verify_password(password, hashed), "❌ Password verification failed!"
    print("  ✅ Correct password verified")
    
    # Verify wrong password
    assert not auth.verify_password("wrong-password", hashed), "❌ Wrong password should fail!"
    print("  ✅ Wrong password rejected")


def test_jwt_tokens():
    """Test JWT token generation and verification."""
    print("\n🎫 Test JWT Tokens")
    
    user_id = "user123"
    username = "admin"
    role = "admin"
    
    # Generate token
    token = auth.generate_jwt(user_id, username, role)
    print(f"  Generated token: {token[:50]}...")
    
    # Decode token
    payload = auth.decode_jwt(token)
    print(f"  Decoded payload: {json.dumps(payload, indent=2, default=str)}")
    
    # Verify token
    payload = auth.verify_jwt(token)
    assert payload["sub"] == user_id, "❌ User ID mismatch!"
    assert payload["username"] == username, "❌ Username mismatch!"
    assert payload["role"] == role, "❌ Role mismatch!"
    print("  ✅ Token verified successfully")
    
    # Test expired token (just decode, don't verify)
    try:
        # Create a token that would be expired (manually craft for demo)
        import jwt as pyjwt
        from datetime import datetime, timedelta
        expired_payload = {
            "sub": user_id,
            "username": username,
            "role": role,
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() - timedelta(hours=1),  # 1 hour ago
        }
        expired_token = pyjwt.encode(
            expired_payload,
            auth.SECRET_KEY,
            algorithm=auth.JWT_ALGORITHM
        )
        
        try:
            auth.verify_jwt(expired_token)
            print("  ❌ Expired token should be rejected!")
        except auth.AuthError as e:
            print(f"  ✅ Expired token rejected: {e}")
    except Exception as e:
        print(f"  ⚠️  Could not test expired token: {e}")


def test_user_registration():
    """Test creating a user account (needs DATABASE_URL set)."""
    print("\n👤 Test User Registration")
    
    if not auth.storage.USE_DB:
        print("  ⚠️  DATABASE_URL not set — using JSON mode")
        print("  💡 To test registration, set DATABASE_URL in .env")
        return
    
    username = f"test_user_{os.urandom(4).hex()}"
    password = "test-password-123"
    
    try:
        # Register new user
        user = auth.create_user_account(
            username=username,
            password=password,
            role="guest",
            email=f"{username}@example.com"
        )
        print(f"  ✅ Created user: {json.dumps(user, indent=2)}")
        
        # Try to register same username again
        try:
            auth.create_user_account(
                username=username,
                password="different-password",
                role="guest"
            )
            print("  ❌ Should have rejected duplicate username!")
        except auth.UserAlreadyExistsError:
            print(f"  ✅ Duplicate username rejected")
        
    except Exception as e:
        print(f"  ⚠️  Registration test failed: {e}")


def test_login():
    """Test login flow (needs DATABASE_URL set)."""
    print("\n🔓 Test Login")
    
    if not auth.storage.USE_DB:
        print("  ⚠️  DATABASE_URL not set — using JSON mode")
        return
    
    # First create a test user
    test_username = f"login_test_{os.urandom(4).hex()}"
    test_password = "secure-password-456"
    
    try:
        auth.create_user_account(
            username=test_username,
            password=test_password,
            role="doctor",
            email=f"{test_username}@example.com",
            doctor_id="dr_test"
        )
        print(f"  ✅ Created test user: {test_username}")
        
        # Test login with correct password
        result = auth.login(test_username, test_password)
        print(f"  ✅ Login successful")
        print(f"    Token: {result['token'][:50]}...")
        print(f"    User: {json.dumps(result['user'], indent=2)}")
        
        # Test login with wrong password
        try:
            auth.login(test_username, "wrong-password")
            print("  ❌ Should have rejected wrong password!")
        except auth.InvalidCredentialsError:
            print("  ✅ Wrong password rejected")
        
        # Test login with non-existent user
        try:
            auth.login("nonexistent-user", test_password)
            print("  ❌ Should have rejected non-existent user!")
        except auth.InvalidCredentialsError:
            print("  ✅ Non-existent user rejected")
            
    except Exception as e:
        print(f"  ❌ Login test failed: {e}")


def main():
    print("=" * 60)
    print("🧪 SHI Authentication System Test")
    print("=" * 60)
    
    test_password_hashing()
    test_jwt_tokens()
    test_user_registration()
    test_login()
    
    print("\n" + "=" * 60)
    print("✨ All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
