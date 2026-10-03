"""Find antiquities-specific details in a listing's text: PAS record, export licence and
provenance.

Deliberately simple keyword matching. Each finding is the sentence that mentions it, so
the analysis can see the context (e.g. "no export licence required" vs "export licence
available"). Price, title and shipping are already fields of the parsed pages.
"""

import re
from dataclasses import dataclass

# "PAS", "P.A.S.", "pas number", "Portable Antiquities Scheme", "portable antiquity no", ...
# A bare lower-case "pas" doesn't count, as it's also an ordinary word.
PAS_MENTION = re.compile(
    r"\bP\.?A\.?S\b"
    r"|(?i:\bpas\s+(?:number|no\b|record|ref|scheme))"
    r"|(?i:\bportable\s+antiquit)"
)
# PAS record ids look like "NMS-6C1F05": an area code, a dash and six hex digits.
PAS_NUMBER = re.compile(r"\b[A-Z]{2,7}-[A-F0-9]{6}\b")
PAS_NUMBER_WINDOW = 100  # how many characters after a PAS mention to look for an id
EXPORT_LICENCE = re.compile(r"\bexport\s+licen[cs]e", re.IGNORECASE)
PROVENANCE = re.compile(r"\bprovenance\b", re.IGNORECASE)


@dataclass
class Details:
    pas: str | None  # sentence mentioning the PAS
    pas_number: str | None  # a PAS record id shortly after a mention of the PAS
    export_licence: str | None  # sentence mentioning an export licence
    provenance: str | None  # sentence mentioning provenance


def find_details(title: str, description: str, item_specifics: dict[str, str]) -> Details:
    """Search the description first, then the title, then the item specifics."""
    specifics = [f"{label}: {value}" for label, value in item_specifics.items()]
    sentences = _sentences(description) + [title] + specifics

    return Details(
        pas=_first_match(PAS_MENTION, sentences),
        pas_number=_pas_number("\n".join(sentences)),
        export_licence=_first_match(EXPORT_LICENCE, sentences),
        provenance=_first_match(PROVENANCE, sentences),
    )


def _sentences(text: str) -> list[str]:
    """Split on line breaks and on full stops, question marks and exclamation marks."""
    parts = re.split(r"\n|(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _pas_number(text: str) -> str | None:
    for mention in PAS_MENTION.finditer(text):
        window = text[mention.end() : mention.end() + PAS_NUMBER_WINDOW]
        if match := PAS_NUMBER.search(window):
            return match.group()
    return None


def _first_match(pattern: re.Pattern, sentences: list[str]) -> str | None:
    return next((s for s in sentences if pattern.search(s)), None)
