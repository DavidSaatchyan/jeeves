from __future__ import annotations



from app.core.compliance.phi_minimization import PHIMinimizer, mask_phi, strip_phi


class TestDetectPhi:
    def test_detects_ssn(self):
        assert PHIMinimizer.is_phi("My SSN is 123-45-6789") is True

    def test_detects_international_phone(self):
        assert PHIMinimizer.is_phi("Call +14155551234") is True

    def test_detects_us_phone(self):
        assert PHIMinimizer.is_phi("Call 4155551234") is True

    def test_detects_email(self):
        assert PHIMinimizer.is_phi("Email me at john@example.com") is True

    def test_detects_name(self):
        assert PHIMinimizer.is_phi("Patient John Smith") is True

    def test_detects_date(self):
        assert PHIMinimizer.is_phi("Born on 01/15/1990") is True

    def test_detects_zip_code(self):
        assert PHIMinimizer.is_phi("ZIP 94105") is True

    def test_returns_false_for_clean_text(self):
        assert PHIMinimizer.is_phi("How are you today?") is False

    def test_returns_false_for_empty_string(self):
        assert PHIMinimizer.is_phi("") is False


class TestStripPhi:
    def test_strips_ssn(self):
        result = strip_phi("My SSN is 123-45-6789")
        assert "[REDACTED]" in result
        assert "123-45-6789" not in result

    def test_strips_email(self):
        result = strip_phi("Contact test@example.com")
        assert "[REDACTED]" in result

    def test_strips_phone(self):
        result = strip_phi("Call +14155551234 now")
        assert "[REDACTED]" in result

    def test_strips_name(self):
        result = strip_phi("Patient John Smith")
        assert "[REDACTED]" in result

    def test_strips_multiple_phi_instances(self):
        result = strip_phi("John Doe at john@example.com, SSN 123-45-6789")
        assert "[REDACTED]" in result
        assert "John Doe" not in result
        assert "john@example.com" not in result
        assert "123-45-6789" not in result

    def test_returns_clean_text_unchanged(self):
        result = strip_phi("Hello, how may I help you?")
        assert result == "Hello, how may I help you?"

    def test_strips_patient_name(self):
        result = PHIMinimizer.strip_phi("Patient Alice Wonderland was seen")
        assert "[REDACTED]" in result
        assert "Alice Wonderland" not in result


class TestMaskPhi:
    def test_masks_sensitive_fields(self):
        data = {"name": "John", "ssn": "123-45-6789", "email": "john@example.com", "age": 30}
        result = mask_phi(data)
        assert result["ssn"] == "[REDACTED]"
        assert result["email"] == "[REDACTED]"
        assert result["name"] == "John"
        assert result["age"] == 30

    def test_masks_specified_fields_only(self):
        data = {"ssn": "123-45-6789", "email": "a@b.com", "phone": "555-0100"}
        result = mask_phi(data, fields=["ssn"])
        assert result["ssn"] == "[REDACTED]"
        assert result["email"] == "a@b.com"

    def test_handles_none_values(self):
        data = {"ssn": None, "name": "John"}
        result = mask_phi(data)
        assert result["ssn"] is None

    def test_returns_copy_not_mutated_original(self):
        data = {"ssn": "123-45-6789"}
        result = mask_phi(data)
        assert result is not data
        assert data["ssn"] == "123-45-6789"

    def test_masks_case_insensitive_keys(self):
        data = {"SSN": "123-45-6789", "Date_Of_Birth": "1990-01-15"}
        result = mask_phi(data)
        assert result["SSN"] == "[REDACTED]"
        assert result["Date_Of_Birth"] == "[REDACTED]"

    def test_masks_additional_phi_fields(self):
        data = {"ssn": "123-45-6789", "passport": "AB123456", "diagnosis": "Hypertension", "address": "123 Main St"}
        result = mask_phi(data)
        assert result["passport"] == "[REDACTED]"
        assert result["diagnosis"] == "[REDACTED]"
        assert result["address"] == "[REDACTED]"

    def test_phiminimizer_mask_phi(self):
        data = {"ssn": "123-45-6789"}
        result = mask_phi(data)
        assert result["ssn"] == "[REDACTED]"


class TestPHIMinimizerMakeSecureLink:
    def test_returns_url_with_all_parts(self):
        link = PHIMinimizer.make_secure_link("patient_record", "rec_123")
        assert link.startswith("/s/")
        assert "patient_record" in link
        assert "rec_123" in link
        assert "token=" in link
        assert "expires=" in link
        assert "sig=" in link

    def test_different_expiry(self):
        link_short = PHIMinimizer.make_secure_link("doc", "1", expire_seconds=60)
        link_long = PHIMinimizer.make_secure_link("doc", "1", expire_seconds=86400)
        assert link_short != link_long


class TestPHIMinimizerTokenize:
    def test_returns_token_dict(self):
        result = PHIMinimizer.tokenize("patient_record", "rec_123")
        assert result["resource_type"] == "patient_record"
        assert result["resource_id"] == "rec_123"
        assert "token" in result
        assert "expires_at" in result

    def test_different_tokens_for_same_resource(self):
        r1 = PHIMinimizer.tokenize("doc", "1")
        r2 = PHIMinimizer.tokenize("doc", "1")
        assert r1["token"] != r2["token"]
