import re

AVENS_ADDRESS_WORDS = [
    "avens", "evans", "hey avens", "okay avens", "listen avens",
    "tell me", "can you", "could you", "open", "search", "remind",
    "what is", "what's", "who is", "how do", "explain", "show me",
    "look at", "play", "stop", "continue",
]

SIDE_TALK_PATTERNS = [
    r"\bmom\b", r"\bmummy\b", r"\bpapa\b", r"\bdad\b",
    r"\bhaan\b", r"\bnahi\b", r"\bachha\b", r"\bruko\b",
    r"\babhi\b", r"\baaya\b", r"\baa raha\b", r"\bkya hua\b",
    r"\bkhana\b", r"\bpaani\b", r"\btheek hai\b",
]

def is_probably_talking_to_avens(text: str, conversation_active: bool = False) -> bool:
    if not text:
        return False

    t = text.lower().strip()

    # Direct address or obvious assistant-style request.
    # These should win even if the sentence is short.
    if any(word in t for word in AVENS_ADDRESS_WORDS):
        return True

    # Obvious side conversation should be ignored even during active window.
    if any(re.search(pattern, t) for pattern in SIDE_TALK_PATTERNS):
        return False

    # Very short replies can be follow-ups only if Avens is already active.
    if len(t.split()) <= 3:
        return conversation_active

    # Questions during active conversation are probably for Avens.
    if conversation_active and any(
        t.startswith(q)
        for q in ["what", "why", "how", "when", "where", "who", "can", "should", "is"]
    ):
        return True

    # Commands during active conversation are probably for Avens.
    if conversation_active and any(
        t.startswith(cmd)
        for cmd in ["open", "search", "play", "show", "tell", "explain", "remind"]
    ):
        return True

    return conversation_active