import pytest
from datetime import datetime, timedelta, timezone

from utils.helpers import (
    create_access_token,
    create_email_verification_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    hash_password,
    is_strong_password,
    is_valid_email,
    is_valid_phone,
    sanitize_input,
    sanitize_mongo_query,
    verify_email_verification_token,
    verify_password,
    verify_password_reset_token,
    now_iso,
    serialize_document,
)
from utils.cache import TTLCache, cache_manager, get_or_create, make_key
from utils.rate_limiter import RateLimiter, rate_limiter
from utils.errors import (
    AppError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    DatabaseError,
    ExternalAPIError,
    MLModelError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)


class TestPasswordHashing:
    def test_hash_and_verify_password_roundtrip(self):
        pw = "SecurePass@123"
        hashed = hash_password(pw)
        assert hashed != pw
        assert hashed.startswith("$2b$")
        assert verify_password(pw, hashed) is True

    def test_verify_password_wrong(self):
        hashed = hash_password("correct@123")
        assert verify_password("wrong@123", hashed) is False

    def test_verify_password_invalid_hash(self):
        assert verify_password("anything", "not-a-hash") is False


class TestPasswordStrength:
    def test_strong_password_ok(self):
        ok, _ = is_strong_password("MyP@ss123")
        assert ok is True

    def test_weak_password_short(self):
        ok, reason = is_strong_password("a")
        assert ok is False
        assert "at least 8" in reason.lower()

    def test_weak_password_no_upper(self):
        ok, _ = is_strong_password("alllower1@")
        assert ok is False

    def test_weak_password_no_lower(self):
        ok, _ = is_strong_password("ALLUPPER1@")
        assert ok is False

    def test_weak_password_no_digit(self):
        ok, _ = is_strong_password("NoDigitsHere@")
        assert ok is False

    def test_weak_password_no_special(self):
        ok, _ = is_strong_password("NoSpecial123")
        assert ok is False


class TestEmailPhoneValidation:
    @pytest.mark.parametrize("email,expected", [
        ("user@example.com", True),
        ("a@b.co", True),
        ("user.name+tag@domain.co.uk", True),
        ("not-an-email", False),
        ("@no-local.com", False),
        ("no-domain@", False),
        ("", False),
        (None, False),
    ])
    def test_email_validation(self, email, expected):
        assert is_valid_email(email) is expected

    @pytest.mark.parametrize("phone,expected", [
        ("+15551234567", True),
        ("15551234567", True),
        ("+44 20 7946 0958", True),
        ("123", False),
        ("not-a-number", False),
        ("", False),
    ])
    def test_phone_validation(self, phone, expected):
        assert is_valid_phone(phone) is expected


class TestSanitization:
    def test_sanitize_strips_html(self):
        assert sanitize_input("<script>alert('xss')</script>") == "scriptalert(xss)/script"

    def test_sanitize_removes_nulls(self):
        assert sanitize_input("hel\0lo") == "hello"

    def test_sanitize_dict(self):
        payload = {"a": "<b>text</b>", "nested": {"c": "<h1>bad</h1>"}}
        cleaned = sanitize_input(payload)
        assert cleaned["a"] == "btext/b"
        assert cleaned["nested"]["c"] == "h1bad/h1"

    def test_sanitize_mongo_query_blocks_dollar_keys(self):
        query = {"$where": "function(){}", "name": "valid"}
        cleaned = sanitize_mongo_query(query)
        assert "$where" not in cleaned
        assert cleaned["name"] == "valid"

    def test_sanitize_mongo_query_allows_safe_operators(self):
        query = {"age": {"$gt": 18, "$lt": 65}}
        cleaned = sanitize_mongo_query(query)
        assert "$gt" in cleaned["age"]
        assert "$lt" in cleaned["age"]


class TestTokens:
    def test_access_token_contains_role(self):
        token = create_access_token("user-1", "analyst")
        payload = decode_token(token)
        assert payload["sub"] == "user-1"
        assert payload["role"] == "analyst"
        assert payload["type"] == "access"

    def test_refresh_token_type(self):
        token = create_refresh_token("user-1", "researcher")
        from config import Config
        payload = decode_token(token, Config.JWT_REFRESH_SECRET)
        assert payload["type"] == "refresh"

    def test_password_reset_token(self):
        token = create_password_reset_token("user@example.com")
        email = verify_password_reset_token(token)
        assert email == "user@example.com"

    def test_invalid_reset_token_returns_none(self):
        assert verify_password_reset_token("not-a-token") is None

    def test_email_verification_token(self):
        token = create_email_verification_token("user@example.com", "id-123")
        result = verify_email_verification_token(token)
        assert result is not None
        assert result["email"] == "user@example.com"
        assert result["user_id"] == "id-123"


class TestUtilsMisc:
    def test_now_iso_format(self):
        value = now_iso()
        parsed = datetime.fromisoformat(value)
        assert isinstance(parsed, datetime)

    def test_serialize_document_objectid_and_datetime(self):
        from bson import ObjectId
        doc = {"_id": ObjectId("507f1f77bcf86cd799439011"), "time": datetime(2025, 1, 1, tzinfo=timezone.utc)}
        result = serialize_document(doc)
        assert result["id"] == "507f1f77bcf86cd799439011"
        assert "time" in result


class TestTTLCache:
    def test_set_and_get(self):
        cache = TTLCache(max_size=10, default_ttl=60)
        cache.set("a", 1)
        assert cache.get("a") == 1

    def test_miss_returns_none(self):
        cache = TTLCache(max_size=10)
        assert cache.get("missing") is None

    def test_expiry_ttl(self):
        cache = TTLCache(max_size=10, default_ttl=0)
        cache.set("a", 1)
        import time; time.sleep(0.01)
        assert cache.get("a") is None

    def test_max_size_evicts_lru(self):
        cache = TTLCache(max_size=2, default_ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        assert cache.size() == 2
        assert cache.get("a") is None

    def test_delete(self):
        cache = TTLCache()
        cache.set("x", 99)
        assert cache.delete("x") is True
        assert cache.delete("x") is False

    def test_get_or_create(self):
        cache = TTLCache()
        called = []
        def factory():
            called.append(1)
            return 42
        value, hit = get_or_create(cache, "k", factory)
        assert value == 42 and hit is False
        value2, hit2 = get_or_create(cache, "k", factory)
        assert value2 == 42 and hit2 is True
        assert len(called) == 1

    def test_make_key(self):
        assert make_key("a", "B", None, " c ") == "a:b::c"


class TestRateLimiter:
    def test_under_limit(self):
        rl = RateLimiter()
        assert rl.check("test-1", limit=3, window=10) is True
        assert rl.check("test-1", limit=3, window=10) is True
        assert rl.check("test-1", limit=3, window=10) is True
        assert rl.check("test-1", limit=3, window=10) is False

    def test_remaining(self):
        rl = RateLimiter()
        assert rl.remaining("test-2", limit=5, window=10) == 5
        rl.check("test-2", limit=5, window=10)
        assert rl.remaining("test-2", limit=5, window=10) == 4

    def test_enforce_raises(self):
        rl = RateLimiter()
        rl.enforce("test-3", limit=1, window=10)
        with pytest.raises(Exception):
            rl.enforce("test-3", limit=1, window=10)


class TestAppErrors:
    def test_app_error_to_dict(self):
        exc = ValidationError("email required")
        d = exc.to_dict()
        assert d["error"] == "validation_error"
        assert d["message"] == "email required"
        assert exc.status_code == 422

    def test_error_subtypes(self):
        assert AuthenticationError().status_code == 401
        assert AuthorizationError().status_code == 403
        assert NotFoundError().status_code == 404
        assert ConflictError().status_code == 409
        assert RateLimitError().status_code == 429
        assert DatabaseError().status_code == 500
        assert ExternalAPIError().status_code == 502
        assert MLModelError().status_code == 500
