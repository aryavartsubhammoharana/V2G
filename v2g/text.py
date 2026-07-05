import re

FILLERS = {
    "um",
    "uh",
    "like",
    "you know",
    "sort of",
    "kind of",
    "basically",
    "actually",
}


def clean_transcript(text):
    normalized = re.sub(r"\s+", " ", text).strip()
    for filler in sorted(FILLERS, key=len, reverse=True):
        normalized = re.sub(rf"\b{re.escape(filler)}\b", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    seen = set()
    unique = []
    for sentence in sentences:
        key = re.sub(r"\W+", "", sentence.lower())
        if key and key not in seen:
            seen.add(key)
            unique.append(sentence.strip())
    return " ".join(unique)


def estimate_tokens(text):
    words = len(re.findall(r"\w+", text))
    return int(words * 1.33)


def limit_text_by_tokens(text, token_limit):
    words = text.split()
    max_words = max(1, int(token_limit / 1.33))
    return " ".join(words[:max_words])


def split_semantic_chunks(text, max_words=1400):
    words = text.split()
    chunks = []
    for index in range(0, len(words), max_words):
        chunk = " ".join(words[index:index + max_words]).strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def seconds_to_timestamp(seconds):
    seconds = int(seconds or 0)
    hours = seconds // 3600
    minutes = seconds % 3600 // 60
    remainder = seconds % 60
    if hours:
        return f"{hours}:{minutes:02d}:{remainder:02d}"
    return f"{minutes}:{remainder:02d}"


def timestamp_to_seconds(value):
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    parts = str(value).split(":")
    try:
        numbers = [int(float(part)) for part in parts]
    except ValueError:
        return 0
    total = 0
    for number in numbers:
        total = total * 60 + number
    return total
