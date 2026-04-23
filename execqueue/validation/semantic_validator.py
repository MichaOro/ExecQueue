"""
Semantic-Validator für Task-Validierung.

Bietet semantische Validierung von Task-Ausgaben:
- Status-Konsistenz (status: done erfordert nicht-leeren evidence)
- Evidence-Qualität (Mindestlänge, Pattern-Matching)
- Cross-field Validierung

Erfüllt REQ-VAL-003 (Status-Konsistenz) und REQ-VAL-004 (Evidence Quality).
"""

import logging
import os
import re
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


# Konfiguration über Environment-Variablen (mit Defaults)
EVIDENCE_MIN_LENGTH = int(os.getenv("VALIDATION_EVIDENCE_MIN_LENGTH", "10"))
EVIDENCE_REQUIRED_FOR_DONE = os.getenv("VALIDATION_EVIDENCE_REQUIRED_FOR_DONE", "true").lower() == "true"
STRICT_MODE = os.getenv("VALIDATION_STRICT_MODE", "false").lower() == "true"

# Patterns für Evidence-Qualitäts-Checks
EVIDENCE_PATTERNS = {
    "test_success": [
        r"test\s+passed",
        r"all\s+tests\s+passed",
        r"no\s+errors",
        r"successfully",
        r"completed\s+successfully",
    ],
    "file_references": [
        r"\.py\b",
        r"\.js\b",
        r"\.ts\b",
        r"line\s+\d+",
        r"file[:\s]",
        r"path[:\s]",
    ],
    "code_changes": [
        r"added\s+\d+\s+file",
        r"modified\s+\d+\s+file",
        r"changed\s+\d+\s+line",
        r"commit",
        r"pushed",
    ],
}

# Patterns für not_done Begründungen
NOT_DONE_PATTERNS = [
    r"error",
    r"failed",
    r"issue",
    r"problem",
    r"cannot",
    r"unable",
    r"missing",
    r"requires",
    r"needs",
    r"blocked",
]


class SemanticValidationError(Exception):
    """Custom exception for semantic validation errors."""
    def __init__(self, message: str, errors: List[str]):
        super().__init__(message)
        self.errors = errors


def validate_status_consistency(data: dict) -> Tuple[bool, List[str]]:
    """
    Validiert die Konsistenz zwischen Status und anderen Feldern.
    
    REQ-VAL-003: Status-Konsistenz
    - status: done erfordert nicht-leeren evidence-String
    - status: not_done erfordert Begründung in summary
    
    Args:
        data: Das validierte JSON-Datum
    
    Returns:
        Tuple aus (ist_valide, Liste von Fehlermeldungen)
    """
    errors = []
    
    status = data.get("status", "").lower()
    summary = data.get("summary", "")
    evidence = data.get("evidence", "")
    
    if status == "done":
        # Bei done muss evidence nicht-leer sein (wenn konfiguriert)
        if EVIDENCE_REQUIRED_FOR_DONE:
            if not evidence or not evidence.strip():
                errors.append(
                    f"Status 'done' erfordert einen nicht-leeren 'evidence'-String. "
                    f"Konfiguration: EVIDENCE_REQUIRED_FOR_DONE={EVIDENCE_REQUIRED_FOR_DONE}"
                )
            elif len(evidence.strip()) < EVIDENCE_MIN_LENGTH:
                errors.append(
                    f"Evidence ist zu kurz ({len(evidence.strip())} Zeichen). "
                    f"Mindestlänge: {EVIDENCE_MIN_LENGTH} Zeichen"
                )
        
        # Summary sollte auch vorhanden sein
        if not summary or not summary.strip():
            errors.append("Status 'done' erfordert eine nicht-leere 'summary'")
    
    elif status == "not_done":
        # Bei not_done muss summary eine Begründung enthalten
        if not summary or not summary.strip():
            errors.append("Status 'not_done' erfordert eine Begründung in 'summary'")
        elif len(summary.strip()) < 10:
            errors.append(
                f"Summary für 'not_done' ist zu kurz ({len(summary.strip())} Zeichen). "
                f"Mindestens 10 Zeichen erforderlich für eine aussagekräftige Begründung"
            )
        
        # Prüfen ob summary eine plausible Begründung enthält
        summary_lower = summary.lower()
        has_reason_pattern = any(
            re.search(pattern, summary_lower) 
            for pattern in NOT_DONE_PATTERNS
        )
        
        if STRICT_MODE and not has_reason_pattern:
            errors.append(
                "Summary für 'not_done' enthält keine erkennbare Begründung. "
                "Verwende Wörter wie 'error', 'failed', 'issue', 'missing', 'requires' etc."
            )
    
    else:
        errors.append(f"Ungültiger Status: '{status}'. Erlaubt: 'done' oder 'not_done'")
    
    return len(errors) == 0, errors


def validate_evidence_quality(data: dict) -> Tuple[bool, List[str]]:
    """
    Validiert die Qualität des Evidence-Strings.
    
    REQ-VAL-004: Evidence Quality
    - Evidence muss konkrete Referenzen enthalten (Dateinamen, Zeilennummern, Test-Outputs)
    - Minimum length requirement (configurable)
    - Pattern-Matching für kritische Artefakte
    
    Args:
        data: Das validierte JSON-Datum
    
    Returns:
        Tuple aus (ist_valide, Liste von Warnmeldungen)
        Hinweis: Dies sind Warnungen, nicht zwingende Fehler.
    """
    warnings = []
    
    status = data.get("status", "").lower()
    evidence = data.get("evidence", "")
    
    # Nur bei status=done prüfen
    if status != "done" or not evidence:
        return True, warnings
    
    evidence_lower = evidence.lower()
    
    # Mindestlänge prüfen
    if len(evidence.strip()) < EVIDENCE_MIN_LENGTH:
        warnings.append(
            f"Evidence ist kürzer als empfohlen ({len(evidence.strip())} < {EVIDENCE_MIN_LENGTH} Zeichen). "
            f"Erwäge konkretere Details hinzuzufügen."
        )
    
    # Prüfen ob Evidence konkrete Referenzen enthält
    has_file_reference = any(
        re.search(pattern, evidence_lower)
        for pattern in EVIDENCE_PATTERNS["file_references"]
    )
    
    has_test_success = any(
        re.search(pattern, evidence_lower)
        for pattern in EVIDENCE_PATTERNS["test_success"]
    )
    
    has_code_changes = any(
        re.search(pattern, evidence_lower)
        for pattern in EVIDENCE_PATTERNS["code_changes"]
    )
    
    # In striktem Modus: Mindestens ein Pattern muss匹配en
    if STRICT_MODE and not (has_file_reference or has_test_success or has_code_changes):
        warnings.append(
            "Evidence enthält keine konkreten Referenzen (Dateinamen, Zeilennummern, Test-Outputs). "
            "Erwäge die Hinzufügung von spezifischen Details wie 'tests/test_x.py passed', 'line 42 updated', etc."
        )
    
    # Nicht-strikte Warnungen
    if not has_file_reference:
        warnings.append(
            "Evidence enthält keine Dateireferenzen. "
            "Konkrete Dateinamen verbessern die Nachvollziehbarkeit."
        )
    
    if not has_test_success and not has_code_changes:
        warnings.append(
            "Evidence enthält keine Test-Erfolgs- oder Code-Änderungs-Patterns. "
            "Erwäge 'tests passed', 'no errors', 'modified file' etc. hinzuzufügen."
        )
    
    return len(warnings) == 0, warnings


def validate_semantics(data: dict) -> Tuple[bool, List[str]]:
    """
    Führt alle semantischen Validierungen durch.
    
    REQ-VAL-003: Status-Konsistenz
    REQ-VAL-004: Evidence Quality
    
    Args:
        data: Das JSON-Datum (bereits schema-valid)
    
    Returns:
        Tuple aus (ist_valide, Liste von Fehler/Warnungs-Meldungen)
        - Fehler führen zu False
        - Warnungen werden zurückgegeben, führen aber nicht zu False
    """
    all_errors = []
    
    # 1. Status-Konsistenz prüfen (kritisch)
    is_consistent, consistency_errors = validate_status_consistency(data)
    if not is_consistent:
        all_errors.extend([f"Status-Konsistenz: {e}" for e in consistency_errors])
    
    # 2. Evidence-Qualität prüfen (warnend)
    _, quality_warnings = validate_evidence_quality(data)
    # Warnungen nur loggen, nicht als Fehler behandeln
    for warning in quality_warnings:
        logger.warning(f"Evidence-Qualitäts-Warnung: {warning}")
        # In STRICT_MODE werden Warnungen zu Fehlern
        if STRICT_MODE:
            all_errors.append(f"Evidence-Qualität: {warning}")
    
    # Rückgabe hängt von Status ab - bei "not_done" ist die Validierung erfolgreich
    # (der Task ist einfach nicht erledigt, aber die Antwort ist valide)
    status = data.get("status", "").lower()
    is_valid = len(all_errors) == 0
    
    return is_valid, all_errors


def get_semantic_validation_details(data: dict) -> dict:
    """
    Gibt detaillierte Informationen über die semantische Validierung zurück.
    
    Args:
        data: Das JSON-Datum
    
    Returns:
        Dict mit Struktur:
        {
            "status_consistency": {
                "valid": bool,
                "errors": [...],
                "checks": {...}
            },
            "evidence_quality": {
                "valid": bool,
                "warnings": [...],
                "patterns_matched": {...}
            }
        }
    """
    status = data.get("status", "").lower()
    summary = data.get("summary", "")
    evidence = data.get("evidence", "")
    
    # Status-Konsistenz Check Details
    consistency_valid, consistency_errors = validate_status_consistency(data)
    
    # Evidence-Qualität Check Details
    evidence_lower = evidence.lower()
    patterns_matched = {
        "test_success": any(
            re.search(p, evidence_lower) 
            for p in EVIDENCE_PATTERNS["test_success"]
        ),
        "file_references": any(
            re.search(p, evidence_lower) 
            for p in EVIDENCE_PATTERNS["file_references"]
        ),
        "code_changes": any(
            re.search(p, evidence_lower) 
            for p in EVIDENCE_PATTERNS["code_changes"]
        ),
    }
    
    _, quality_warnings = validate_evidence_quality(data)
    
    return {
        "status_consistency": {
            "valid": consistency_valid,
            "errors": consistency_errors,
            "checks": {
                "status": status,
                "has_summary": bool(summary and summary.strip()),
                "has_evidence": bool(evidence and evidence.strip()),
                "evidence_length": len(evidence) if evidence else 0,
                "evidence_min_length": EVIDENCE_MIN_LENGTH,
            }
        },
        "evidence_quality": {
            "valid": len(quality_warnings) == 0,
            "warnings": quality_warnings,
            "patterns_matched": patterns_matched,
        }
    }
