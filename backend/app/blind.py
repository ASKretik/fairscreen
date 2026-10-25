"""Deterministic redaction safety net (SPEC §5, layer 2).

Runs after the parse call. Scans every string in the blind profile and removes
emails, URLs, phone numbers, the candidate's name and location, drops gendered
titles and neutralises gendered pronouns. Every replacement is counted.
"""

import re

from app.models import BlindProfile, Education, Experience, Identity, ParsedResume, Project

PLACEHOLDER = "[redacted]"
# Marks a removed span while scrubbing. U+2063 is not a word character, so
# later whole-word patterns cannot match into it; it becomes PLACEHOLDER at the end.
_MARK = "⁣"

EMAIL_RE = re.compile(r"[\w.+%-]+@[\w-]+(?:\.[\w-]+)+")

# Bare domains need a path, and the TLD list leaves out "net"/"tech" on purpose,
# so skills such as "ASP.NET/C#" and degrees such as "B.Tech/M.Tech" survive.
URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s<>\"']+"
    r"|\b(?:[a-z0-9-]+\.)+(?:com|org|io|dev|me|co|in|ai|app|xyz|site|page|info)/[^\s<>\"']*"
    r"|\b(?:linkedin|github|gitlab|bitbucket|behance|dribbble|medium|kaggle|leetcode"
    r"|stackoverflow|twitter|x|instagram|facebook)\.com\b[^\s<>\"']*",
    re.IGNORECASE,
)
_URL_TRAILING = ".,;:!?)]}'\""

# Shapes of real phone numbers rather than "any long digit run", so year ranges
# ("2019-2023"), versions ("3.11") and grades ("8.7/10") are left alone.
PHONE_RE = re.compile(
    r"(?<![\w+])(?:"
    r"\+\d{1,3}[\s.\-]?(?:\(\d{1,4}\)[\s.\-]?)?\d{2,5}(?:[\s.\-]?\d{2,5}){1,3}"  # +91 98765 43210
    r"|\(\d{3}\)\s?\d{3}[\s.\-]?\d{4}"                                           # (555) 123-4567
    r"|\d{3}[\s.\-]\d{3}[\s.\-]\d{4}"                                            # 555-123-4567
    r"|\d{5}[\s\-]\d{5}"                                                         # 98765 43210
    r"|\d{10,13}"                                                                # 9876543210
    r")(?!\w)"
)

# Case-sensitive so the degree "MS" is never touched.
TITLE_RE = re.compile(r"\b(?:Mr|Mrs|Ms)\.\s*|\b(?:Mr|Mrs|Ms|Miss)\s+(?=[A-Z])")

_PRONOUN_MAP = {
    "he": "they",
    "she": "they",
    "him": "them",
    "his": "their",
    "hers": "theirs",
    "himself": "themselves",
    "herself": "themselves",
    "her": None,  # "them" or "their", decided by the next word
}
# Only lowercase and Capitalised forms, so acronyms like "HIS" or "HE" are kept.
PRONOUN_RE = re.compile(
    r"\b(?:" + "|".join(f"{w}|{w.capitalize()}" for w in sorted(_PRONOUN_MAP, key=len, reverse=True)) + r")\b"
)
# Words after which "her" is an object ("promoted her to lead") rather than a possessive ("her team").
_HER_OBJECT_NEXT = {
    "the", "a", "an", "to", "for", "in", "on", "at", "with", "by", "from", "as", "and", "or",
    "of", "into", "about", "after", "before", "during", "over", "through", "that", "this",
    "these", "those", "up", "out", "off", "back", "again", "while", "when", "but",
}
_NEXT_WORD_RE = re.compile(r"\s*([A-Za-z']+)?")
_AGREEMENT_RE = re.compile(r"\b(they|They) (is|was|has|does)\b")
_AGREEMENT = {"is": "are", "was": "were", "has": "have", "does": "do"}

_TITLE_TOKENS = {"mr", "mrs", "ms", "miss", "dr", "prof"}


def _phrase_re(phrase: str) -> re.Pattern[str]:
    """Whole-word, case-insensitive match of a phrase, tolerant of spacing."""
    parts = [re.escape(p) for p in phrase.split()]
    return re.compile(r"(?<!\w)" + r"\s+".join(parts) + r"(?!\w)", re.IGNORECASE)


def _name_tokens(name: str) -> list[str]:
    tokens: set[str] = set()
    for raw in name.split():
        for t in (raw, *raw.split("-")):
            t = t.strip(".,;:()[]'\"")
            if len(t) > 2 and t.lower() not in _TITLE_TOKENS:
                tokens.add(t)
    return sorted(tokens, key=len, reverse=True)


def _location_parts(location: str) -> list[str]:
    parts = (p.strip(" .") for p in re.split(r"[,/|;]|\s-\s", location))
    return sorted(
        {p for p in parts if len(p) > 2 and p.lower() != location.strip().lower()}, key=len, reverse=True
    )


def _phone_re(phone: str) -> re.Pattern[str] | None:
    """The identity's own number in any formatting (spaces, dots, dashes, brackets, country code)."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 7:
        return None
    sep = r"[\s.\-()]*"
    return re.compile(r"(?<!\d)(?:\+?\d{1,3}" + sep + r")?" + sep.join(digits[-10:]) + r"(?!\d)")


def _neutral_pronoun(m: re.Match[str]) -> str:
    word = m.group(0)
    low = word.lower()
    repl = _PRONOUN_MAP[low]
    if repl is None:  # "her"
        nxt = _NEXT_WORD_RE.match(m.string, m.end()).group(1)
        repl = "them" if nxt is None or nxt.lower() in _HER_OBJECT_NEXT else "their"
    return repl.capitalize() if word[0].isupper() else repl


def neutralise_pronouns(text: str) -> tuple[str, int]:
    """Replace gendered pronouns with they/them/their/theirs/themselves. Returns (text, count)."""
    new, n = PRONOUN_RE.subn(_neutral_pronoun, text)
    if n:
        new = _AGREEMENT_RE.sub(lambda m: f"{m.group(1)} {_AGREEMENT[m.group(2)]}", new)
    return new, n


def _strip_url(m: re.Match[str]) -> str:
    url = m.group(0)
    kept = url.rstrip(_URL_TRAILING)
    return _MARK + url[len(kept):]


_MARK_RUN_RE = re.compile(f"{_MARK}(?:[\\s,]*{_MARK})*")


def _finish(text: str) -> str:
    text = _MARK_RUN_RE.sub(PLACEHOLDER, text)
    text = re.sub(r"\s+([,.;:)])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()


class _Redactor:
    def __init__(self, identity: Identity):
        self.count = 0
        variants = {v for link in identity.links if link.strip()
                    for v in (link.strip(), re.sub(r"^https?://(www\.)?", "", link.strip(), flags=re.I))}
        self._links = [_phrase_re(v) for v in sorted(variants, key=len, reverse=True)]  # full URL first
        self._phone = _phone_re(identity.phone) if identity.phone else None
        self._full_name = _phrase_re(identity.name) if identity.name and identity.name.strip() else None
        self._name_tokens = [_phrase_re(t) for t in _name_tokens(identity.name or "")]
        loc = (identity.location or "").strip()
        self._location = _phrase_re(loc) if len(loc) > 2 else None
        self._location_parts = [_phrase_re(p) for p in _location_parts(loc)] if loc else []

    def _sub(self, pattern: re.Pattern[str], text: str, repl=_MARK) -> str:
        new, n = pattern.subn(repl, text)
        self.count += n
        return new

    def scrub(self, text: str, free_text: bool = False) -> str:
        t = self._sub(EMAIL_RE, text)
        for link in self._links:
            t = self._sub(link, t)
        t = self._sub(URL_RE, t, _strip_url)
        if self._phone:
            t = self._sub(self._phone, t)
        t = self._sub(PHONE_RE, t)
        t = self._sub(TITLE_RE, t, "")
        if self._full_name:
            t = self._sub(self._full_name, t)
        if self._location:
            t = self._sub(self._location, t)
        for token in self._name_tokens:
            t = self._sub(token, t)
        # City/state/country on their own are removed from free text only. Structured
        # fields keep them, because institution and employer names often contain a
        # city ("University of Mumbai") and college is visible by policy (SPEC §5).
        if free_text:
            for part in self._location_parts:
                t = self._sub(part, t)
        t, n = neutralise_pronouns(t)
        self.count += n
        return text if t == text else _finish(t)  # untouched strings keep their exact formatting

    def scrub_list(self, items: list[str]) -> list[str]:
        out = (self.scrub(s) for s in items)
        return [s for s in out if s and s != PLACEHOLDER]

    def scrub_fields(self, data: dict, free_text: frozenset[str] = frozenset()) -> dict:
        return {k: self.scrub(v, k in free_text) if isinstance(v, str) else v for k, v in data.items()}


def redact(parsed: ParsedResume) -> tuple[BlindProfile, Identity, int]:
    """Return (blind profile, identity, redaction_count)."""
    r = _Redactor(parsed.identity)
    p = parsed.profile
    profile = BlindProfile(
        headline=r.scrub(p.headline, free_text=True),
        education=[Education(**r.scrub_fields(e.model_dump())) for e in p.education],
        experience=[
            Experience(**r.scrub_fields(e.model_dump(), frozenset({"summary"}))) for e in p.experience
        ],
        total_experience_months=p.total_experience_months,
        skills=r.scrub_list(p.skills),
        projects=[
            Project(**r.scrub_fields(pr.model_dump(), frozenset({"title", "summary"}))) for pr in p.projects
        ],
        certifications=r.scrub_list(p.certifications),
    )
    return profile, parsed.identity.model_copy(deep=True), r.count
