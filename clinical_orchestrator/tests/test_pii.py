from clinical_orchestrator.core.pii import mask, mask_dict


def test_mask_email_phone_ssn():
    text = "Contact john.doe@example.com or 415-555-0123. SSN: 123-45-6789."
    out = mask(text)
    assert "[REDACTED:EMAIL]" in out
    assert "[REDACTED:PHONE]" in out
    assert "[REDACTED:SSN]" in out
    assert "john.doe" not in out
    assert "415-555-0123" not in out


def test_mask_mrn_and_date():
    text = "MRN: 12345 visited on 2024-01-15"
    out = mask(text)
    assert "[REDACTED:MRN]" in out
    assert "[REDACTED:DOB]" in out


def test_mask_aggressive_names():
    text = "John Smith arrived"
    out = mask(text, aggressive=True)
    assert "[REDACTED:NAME]" in out


def test_mask_dict_recursive():
    data = {"a": "email me at x@y.com", "b": [{"c": "Call 415-555-0123"}]}
    out = mask_dict(data)
    assert "[REDACTED:EMAIL]" in out["a"]
    assert "[REDACTED:PHONE]" in out["b"][0]["c"]
