from __future__ import annotations


from app.integrations.crm.exceptions import CrmAuthError, CrmConnectionError, CrmNotFoundError, CrmRateLimitError


class TestCrmConnectionError:
    def test_default_attributes(self):
        exc = CrmConnectionError("zoho", "get_patient", "Connection refused")
        assert exc.provider == "zoho"
        assert exc.operation == "get_patient"
        assert exc.message == "Connection refused"

    def test_str_format(self):
        exc = CrmConnectionError("hubspot", "create_appointment", "timeout")
        assert "[hubspot] create_appointment: timeout" in str(exc)

    def test_is_exception(self):
        exc = CrmConnectionError("test", "op", "msg")
        assert isinstance(exc, Exception)

    def test_empty_provider(self):
        exc = CrmConnectionError("", "op", "msg")
        assert str(exc).startswith("[]")

    def test_empty_message(self):
        exc = CrmConnectionError("zoho", "op", "")
        assert "[zoho] op: " == str(exc)


class TestCrmAuthError:
    def test_inherits_from_connection_error(self):
        exc = CrmAuthError("zoho", "refresh_token", "Invalid grant")
        assert isinstance(exc, CrmConnectionError)
        assert isinstance(exc, Exception)

    def test_attributes(self):
        exc = CrmAuthError("zoho", "refresh_token", "invalid_grant")
        assert exc.provider == "zoho"
        assert exc.operation == "refresh_token"
        assert exc.message == "invalid_grant"

    def test_str_format(self):
        exc = CrmAuthError("zoho", "token", "expired")
        assert "zoho" in str(exc)
        assert "token" in str(exc)
        assert "expired" in str(exc)


class TestCrmNotFoundError:
    def test_inherits_from_connection_error(self):
        exc = CrmNotFoundError("salesforce", "get_patient", "Not found")
        assert isinstance(exc, CrmConnectionError)
        assert isinstance(exc, Exception)

    def test_attributes(self):
        exc = CrmNotFoundError("zoho", "GET", "Resource not found: /crm/v7/Contacts/999")
        assert exc.provider == "zoho"
        assert exc.operation == "GET"
        assert exc.message == "Resource not found: /crm/v7/Contacts/999"

    def test_str_contains_message(self):
        exc = CrmNotFoundError("hubspot", "find", "No match")
        assert "No match" in str(exc)


class TestCrmRateLimitError:
    def test_inherits_from_connection_error(self):
        exc = CrmRateLimitError("zoho", "POST", "Rate limit exceeded")
        assert isinstance(exc, CrmConnectionError)
        assert isinstance(exc, Exception)

    def test_attributes(self):
        exc = CrmRateLimitError("zoho", "GET", "Too many requests")
        assert exc.provider == "zoho"
        assert exc.operation == "GET"
        assert exc.message == "Too many requests"

    def test_str_contains_message(self):
        exc = CrmRateLimitError("zoho", "POST", "rate_limit")
        assert "rate_limit" in str(exc)

    def test_distinct_from_other_errors(self):
        rate = CrmRateLimitError("zoho", "op", "rate")
        auth = CrmAuthError("zoho", "op", "auth")
        nf = CrmNotFoundError("zoho", "op", "nf")
        assert not isinstance(rate, CrmAuthError)
        assert not isinstance(rate, CrmNotFoundError)
        assert not isinstance(auth, CrmRateLimitError)
        assert not isinstance(auth, CrmNotFoundError)
        assert not isinstance(nf, CrmRateLimitError)
        assert not isinstance(nf, CrmAuthError)
