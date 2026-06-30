from typing import Iterable


class SecurityGate:
    """Lightweight deterministic text gate for blocked phrases."""

    def __init__(self, blacklist: Iterable[str], threshold: float = 0.85):
        self.blacklist = [word.lower() for word in blacklist if word.strip()]
        self.threshold = threshold

    def is_malicious(self, text: str) -> tuple[bool, str]:
        """Return whether text contains a configured blocked phrase."""

        text_lower = text.lower()
        for blocked_phrase in self.blacklist:
            if blocked_phrase in text_lower:
                return True, f"Deterministic match: {blocked_phrase}"
        return False, ""
