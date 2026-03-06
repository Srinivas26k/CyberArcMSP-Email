import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.payload_sanitizer import PayloadSanitizer

def test_truncate_context_keeps_data_if_within_limit():
    lead = {
        "first_name": "John",
        "company": "Acme Corp",
        "linkedin": "https://linkedin.com/in/john",
        "website": "acme.com",
        "employees": "500",
        "location": "New York",
        "industry": "Tech"
    }
    prompt = "Write an email to John at Acme Corp."
    # With a high limit, nothing should be truncated
    truncated = PayloadSanitizer.truncate_context(lead, prompt, max_chars=4000)
    assert truncated["linkedin"] == "https://linkedin.com/in/john"
    assert truncated["industry"] == "Tech"

def test_truncate_context_removes_fields_if_exceeds_limit():
    lead = {
        "first_name": "John",
        "company": "Acme Corp",
        "linkedin": "https://linkedin.com/in/john",
        "website": "acme.com",
        "employees": "500",
        "location": "New York",
        "industry": "Tech"
    }
    # Large prompt to force truncation
    prompt = "A" * 3000
    # Set max_chars such that the prompt itself takes most of the space
    limit = 3000 + 100 
    truncated = PayloadSanitizer.truncate_context(lead, prompt, max_chars=limit)
    
    # Should slice off less critical fields
    assert truncated["linkedin"] == ""
    assert truncated["website"] == ""
    # "first_name" is not in the truncation list, so it stays untouched
    assert truncated["first_name"] == "John"

def test_spam_keyword_filter():
    clean_text = "I would like to discuss our enterprise software solutions."
    spam_text = "Click here to double your income immediately! It's 100% free!"
    
    clean_matches = PayloadSanitizer.has_spam_keywords(clean_text)
    assert len(clean_matches) == 0
    
    spam_matches = PayloadSanitizer.has_spam_keywords(spam_text)
    assert "click here" in spam_matches
    assert "double your income" in spam_matches
    assert "100% free" in spam_matches

def test_personalization_validator():
    # Both included
    good_text = "Hi John, I saw Acme Corp is doing great."
    assert PayloadSanitizer.verify_personalization(good_text, "John", "Acme Corp") is True
    
    # Missing first name
    bad_name_text = "Hi Friend, I saw Acme Corp is doing great."
    assert PayloadSanitizer.verify_personalization(bad_name_text, "John", "Acme Corp") is False
    
    # Missing company
    bad_company_text = "Hi John, I saw your company is doing great."
    assert PayloadSanitizer.verify_personalization(bad_company_text, "John", "Acme Corp") is False
    
    # Case insensitive
    case_text = "Hi JOHN, I saw acme corp is doing great."
    assert PayloadSanitizer.verify_personalization(case_text, "John", "Acme Corp") is True
