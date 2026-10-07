import re
import uuid
from collections import Counter


MAX_NAME_LENGTH = 60
UNIQUE_SUFFIX_LENGTH = 6


_TRANSLITERATION = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
)

_TASK_PREFIX = re.compile(r"^(?:aufgabe|task|prompt)\s*(?:#?\d+)?\s*[:\-]?\s*", re.I)
_TOPIC_SUFFIXES = (
    "steuerung", "zaehler", "addierer", "automat", "ampel", "uart", "fifo",
    "multiplexer", "decoder", "encoder", "regler", "sensor", "display",
)
_STOP_WORDS = {
    "aber", "alle", "auch", "auf", "aus", "board", "dabei", "damit", "dann",
    "das", "dass", "dem", "den", "der", "des", "die", "dies", "diese",
    "ein", "eine", "einen", "einer", "eines", "erstellen", "fuer", "haben",
    "hier", "ich", "ihre", "ihr", "im", "in", "ist", "kann", "koennen",
    "mit", "nach", "nicht", "oder", "soll", "sollen", "und", "ueber", "um",
    "verwende", "wird", "wie", "wobei", "zu", "zum", "zur", "zwischen",
    "aufgabe", "prompt", "projekt", "schaltung", "vhdl", "fpga", "hardware",
    "system", "design", "digitaler", "digitales", "led", "arty", "digilent",
}


def sanitize(name: str) -> str:
    """Normalize a name: lowercase, dashes instead of separators, ASCII-safe charset.

    Umlauts are transliterated (ae/oe/ue/ss) so the result is compatible with
    the ASCII project-ID policy enforced by the filesystem service.
    """
    name = (name or "").lower().strip()
    name = name.translate(_TRANSLITERATION)
    name = re.sub(r"^(?:projektname|projekt|project name)\s*[:\-]\s*", "", name)
    name = re.sub(r"^(?:aufgabe|task|prompt)\s*(?:#?\d+)?\s*[:\-]\s*", "", name)
    name = re.sub(
        r"^(?:(?:optimiert|verbessert|detailliert|ausfuehrlich)\w*\s+)?"
        r"(?:prompt|promptvorlage|aufgabe|task)\s+(?:fuer|zum|zur|for)\s+",
        "",
        name,
    )
    name = re.sub(
        r"^(?:bitte\s+)?(?:entwickle|entwickele|erstelle|baue|implementiere|"
        r"generiere|erzeuge|create|build|design)\s+",
        "",
        name,
    )
    name = re.sub(r"^(?:einen?|eine|den|die|das)\s+", "", name)
    name = re.sub(
        r"^(?:synthetisierbar\w*|synthesierbar\w*|optimier\w*|"
        r"verbesser\w*|prompt\w*)\s+",
        "",
        name,
    )
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")
    return name[:MAX_NAME_LENGTH].rstrip("-")


def slugify(request: str) -> str:
    """Derive a file-safe name from the raw request text."""
    cleaned = _TASK_PREFIX.sub("", (request or "").strip())
    return sanitize(cleaned) or "projekt"


def extract_project_topic(request: str) -> str:
    """Extract a distinctive circuit topic when one is explicitly present."""
    text = (request or "").lower().translate(_TRANSLITERATION)
    words = re.findall(r"\b[a-z0-9]+\b", text)
    topics = [
        word for word in words
        if len(word) >= 4 and word not in _STOP_WORDS
        and any(word.endswith(suffix) for suffix in _TOPIC_SUFFIXES)
    ]
    if topics:
        counts = Counter(topics)
        topic = max(counts, key=lambda word: (counts[word], len(word)))
        return sanitize(topic)
    return ""


def derive_project_name(request: str) -> str:
    """Prefer a distinctive circuit topic over prompt numbering or boilerplate."""
    topic = extract_project_topic(request)
    if topic:
        return topic

    name = slugify(request)
    if re.fullmatch(r"(?:aufgabe|task|prompt)(?:-\d+)?", name):
        return "projekt"
    return name


def make_unique(name: str) -> str:
    """Append a short unique suffix so project folders never collide."""
    suffix = uuid.uuid4().hex[:UNIQUE_SUFFIX_LENGTH]
    return f"{name}-{suffix}"
