from typing import Dict, Any, List

class PayloadSanitizationError(Exception):
    """Raised when a payload fails sanitization (e.g. spam keywords detected)."""
    pass

class PersonalizationError(Exception):
    """Raised when the LLM fails to include required personalization tokens."""
    pass

class PayloadSanitizer:
    # A list of common spam trigger words to flag
    SPAM_KEYWORDS = {
        "double your income",
        "investment opportunity",
        "act now!",
        "guaranteed return",
        "100% free",
        "click here",
        "dear friend",
        "urgent",
        "winner",
        "no obligation",
    }

    @staticmethod
    def truncate_context(lead_data: Dict[str, Any], prompt_template: str, max_chars: int = 4000) -> Dict[str, Any]:
        """
        Token Truncation:
        Checks the combined length of the 'Lead Info' + 'User Prompt'.
        Truncates the least relevant lead data (e.g., website, linkedin, location, employees, or bio) 
        if it exceeds the approximate character limit (which simulates a token limit context window).
        
        Returns a (possibly constrained) copy of the lead_data.
        """
        copied_lead = dict(lead_data)
        
        # Priority of fields to remove if context is too large, from least to most important
        truncation_order = ["linkedin", "website", "employees", "location", "industry"]

        def _get_estimated_size(current_lead: Dict[str, Any]) -> int:
            lead_str = str(current_lead)
            return len(lead_str) + len(prompt_template)

        for field in truncation_order:
            if _get_estimated_size(copied_lead) <= max_chars:
                break
            
            if field in copied_lead and copied_lead[field]:
                # Nullify or shorten the field to save space
                copied_lead[field] = ""
                
        return copied_lead

    @staticmethod
    def has_spam_keywords(text: str) -> List[str]:
        """
        Spam Keyword Filter:
        Scans the generated LLM draft for 'spammy' trigger words.
        Returns a list of matched spam keywords.
        """
        text_lower = text.lower()
        matched = []
        for kw in PayloadSanitizer.SPAM_KEYWORDS:
            if kw in text_lower:
                matched.append(kw)
        return matched

    @staticmethod
    def verify_personalization(text: str, first_name: str, company: str) -> bool:
        """
        Personalization Validator:
        Ensures that the LLM actually used the first_name and company placeholders
        provided in the context. Returns True if both are present in the text (case-insensitive).
        If either was empty in the lead data, it counts as 'passed' for that field.
        """
        text_lower = text.lower()
        
        if first_name and first_name.lower() not in text_lower:
            return False
            
        if company and company.lower() not in text_lower:
            return False
            
        return True
