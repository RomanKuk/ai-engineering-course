import re
import logging
from pathlib import Path
from fastapi import HTTPException

MAX_LENGTH = 4000

_PATTERNS_FILE = Path(__file__).parent.parent / "data" / "injection_patterns.txt"


def _load_patterns() -> list[re.Pattern]:
    if not _PATTERNS_FILE.exists():
        return []
    patterns = []
    for line in _PATTERNS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(re.compile(line, re.IGNORECASE))
    return patterns


_PATTERNS: list[re.Pattern] = _load_patterns()

logging.basicConfig()
_req_log = logging.getLogger("suspicious_requests")
_req_log.addHandler(logging.FileHandler("suspicious_requests.log"))
_req_log.setLevel(logging.WARNING)

_out_log = logging.getLogger("suspicious_responses")
_out_log.addHandler(logging.FileHandler("suspicious_responses.log"))
_out_log.setLevel(logging.WARNING)


def check_input(text: str) -> str:
    if len(text) > MAX_LENGTH:
        raise HTTPException(status_code=400, detail=f"Input exceeds {MAX_LENGTH} characters")
    for pat in _PATTERNS:
        if pat.search(text):
            _req_log.warning("Suspicious input detected: %.200s", text)
            raise HTTPException(status_code=400, detail="Suspicious input detected")
    return text


def check_output(text: str) -> bool:
    for pat in _PATTERNS:
        if pat.search(text):
            _out_log.warning("Suspicious output detected: %.200s", text)
            return True
    return False
