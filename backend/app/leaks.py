"""Check that a candidate's public data contains none of its identity (a test of blind.py on real output)."""

import json
import re
from typing import Any

from app.models import Identity


def identity_needles(identity: Identity) -> list[str]:
    """Strings that must not appear in the blind data: full name, name parts over 2 chars, email, phone digits, links."""
    needles: list[str] = []
    if identity.name:
        needles.append(identity.name)
        needles += [t.strip(".,") for t in identity.name.split() if len(t.strip(".,")) > 2 and t.lower() not in {"mr.", "mrs.", "ms."}]
    if identity.email:
        needles.append(identity.email)
    if identity.phone and len(re.sub(r"\D", "", identity.phone)) >= 7:
        needles.append(re.sub(r"\D", "", identity.phone)[-10:])  # national number, without country code
    needles += [re.sub(r"^https?://(www\.)?", "", link) for link in identity.links if link]
    return needles


def find_leaks(public: Any, identity: Identity) -> list[str]:
    """Identity strings found in `public` (any JSON-able data). Phone digits are matched ignoring separators."""
    blob = json.dumps(public, default=str, ensure_ascii=False)
    lowered = blob.lower()
    leaks = []
    for needle in identity_needles(identity):
        if needle.isdigit():
            if re.search(r"[\s().\-]*".join(needle) + r"(?!\d)", blob):
                leaks.append(f"phone …{needle[-4:]}")
        elif re.search(r"(?<!\w)" + re.escape(needle.lower()) + r"(?!\w)", lowered):
            leaks.append(needle)
    return leaks
