"""
Task-Validator für ExecQueue.

Haupt-Validator, der Schema- und Semantic-Validierung orchestriert.
Bietet eine einheitliche Schnittstelle für die Task-Ergebnis-Validierung.

Erfüllt REQ-VAL-001 bis REQ-VAL-008 (Multi-Pass Validation).
"""

import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from execqueue.validation.schema_validator import (
    extract_json_from_output,
    get_schema_errors_detailed,
    validate_schema,
)
from execqueue.validation.semantic_validator import (
    get_semantic_validation_details,
    validate_semantics,
)
from execqueue.validation.policy_loader import get_retry_policy, get_policy

logger = logging.getLogger(__name__)


class ValidationErrorType:
    """Enumeration der möglichen Fehlertypen."""
    NONE = "none"
    PARSING = "parsing"
    SEMANTIC = "semantic"
    CRITICAL = "critical"


@dataclass
class TaskValidationResult:
    """
    Ergebnis der Task-Validierung.
    
    Erweitert das原有 TaskValidationResult um detaillierte Fehlerinformationen
    für differenzierte Retry-Logik.
    """
    is_done: bool
    normalized_status: str
    summary: str
    raw_status: Optional[str]
    evidence: str = ""
    
    # Neue Felder für Hardening
    error_type: str = ValidationErrorType.NONE
    error_details: List[str] = field(default_factory=list)
    validation_passes: dict = field(default_factory=dict)
    retry_count: int = 0
    backoff_seconds: float = 0.0
    
    # Audit-Informationen
    schema_version: str = "1.0.0"
    raw_output_snapshot: str = ""
    
    @property
    def should_retry(self) -> bool:
        """Prüft ob ein Retry möglich ist basierend auf error_type."""
        if self.error_type == ValidationErrorType.CRITICAL:
            return False
        if self.error_type == ValidationErrorType.NONE:
            return False
        
        # Für parsing/semantic Fehler prüfen wir die Policy
        return self.retry_count < get_retry_policy(self.error_type).max_retries
    
    @property
    def is_critical(self) -> bool:
        """Prüft ob es sich um einen kritischen Fehler handelt."""
        return self.error_type == ValidationErrorType.CRITICAL


def validate_task_result(
    output: str,
    retry_count: int = 0,
    schema_version: str = "1.0.0"
) -> TaskValidationResult:
    """
    Validiert das Ergebnis einer Task-Ausführung.
    
    Multi-Pass Validierung:
    1. Pass: Schema-Validierung (JSON-Struktur)
    2. Pass: Semantische Validierung (Inhaltliche Korrektheit)
    
    REQ-VAL-001: JSON Schema Enforcement
    REQ-VAL-002: Output Parsing Robustheit
    REQ-VAL-003: Status-Konsistenz
    REQ-VAL-004: Evidence Quality
    REQ-VAL-005: Differenzierte Retry-Logik
    REQ-VAL-008: Multi-Pass Validation
    
    Args:
        output: Der zu validierende Output-String
        retry_count: Aktuelle Retry-Anzahl (für Backoff-Berechnung)
        schema_version: Version des zu verwendenden Schemas
    
    Returns:
        TaskValidationResult mit Validierungsergebnis und Fehlerdetails
    """
    # Audit-Trail: Snapshot des Outputs
    raw_output_snapshot = output[:1000] if output else ""
    
    # === PASS 1: Schema-Validierung ===
    schema_valid, schema_errors = validate_schema(output, schema_version)
    
    if not schema_valid:
        # Parsing-Fehler
        logger.warning(f"Schema-Validierung fehlgeschlagen: {schema_errors}")
        
        # Berechne Backoff
        from execqueue.validation.policy_loader import calculate_backoff_seconds
        backoff = calculate_backoff_seconds(ValidationErrorType.PARSING, retry_count)
        
        return TaskValidationResult(
            is_done=False,
            normalized_status="not_done",
            summary=f"Schema-Validierung fehlgeschlagen: {'; '.join(schema_errors[:3])}",
            raw_status=None,
            evidence="",
            error_type=ValidationErrorType.PARSING,
            error_details=schema_errors,
            validation_passes={"schema": False, "semantic": None},
            retry_count=retry_count,
            backoff_seconds=backoff,
            schema_version=schema_version,
            raw_output_snapshot=raw_output_snapshot,
        )
    
    # JSON erfolgreich extrahiert - parsen für semantische Validierung
    json_str = extract_json_from_output(output)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # Sollte nicht passieren, da Schema-Validierung bestanden
        logger.error("JSON-Parsing nach Schema-Validierung fehlgeschlagen")
        return TaskValidationResult(
            is_done=False,
            normalized_status="not_done",
            summary="Interne Fehler: JSON konnte nach Schema-Validierung nicht geparsed werden",
            raw_status=None,
            evidence="",
            error_type=ValidationErrorType.CRITICAL,
            error_details=["JSON-Parsing nach Schema-Validierung fehlgeschlagen"],
            validation_passes={"schema": True, "semantic": None},
            retry_count=retry_count,
            schema_version=schema_version,
            raw_output_snapshot=raw_output_snapshot,
        )
    
    # === PASS 2: Semantische Validierung ===
    semantic_valid, semantic_errors = validate_semantics(data)
    
    if not semantic_valid:
        # Semantische Fehler
        logger.warning(f"Semantische Validierung fehlgeschlagen: {semantic_errors}")
        
        from execqueue.validation.policy_loader import calculate_backoff_seconds
        backoff = calculate_backoff_seconds(ValidationErrorType.SEMANTIC, retry_count)
        
        return TaskValidationResult(
            is_done=False,
            normalized_status="not_done",
            summary=f"Semantische Validierung fehlgeschlagen: {'; '.join(semantic_errors[:3])}",
            raw_status=data.get("status"),
            evidence=data.get("evidence", ""),
            error_type=ValidationErrorType.SEMANTIC,
            error_details=semantic_errors,
            validation_passes={"schema": True, "semantic": False},
            retry_count=retry_count,
            backoff_seconds=backoff,
            schema_version=schema_version,
            raw_output_snapshot=raw_output_snapshot,
        )
    
    # === Validierung bestanden ===
    logger.info("Task-Validierung erfolgreich")
    
    # is_done hängt vom status-Feld ab, nicht von der Validierung
    status = data.get("status", "").lower()
    is_done = status == "done"
    
    return TaskValidationResult(
        is_done=is_done,
        normalized_status=status,
        summary=data.get("summary", "Task completed successfully" if is_done else "Task not completed"),
        raw_status=status,
        evidence=data.get("evidence", ""),
        error_type=ValidationErrorType.NONE,
        error_details=[],
        validation_passes={"schema": True, "semantic": True},
        retry_count=retry_count,
        backoff_seconds=0.0,
        schema_version=schema_version,
        raw_output_snapshot=raw_output_snapshot,
    )


def validate_task_result_with_details(
    output: str,
    retry_count: int = 0,
    schema_version: str = "1.0.0"
) -> TaskValidationResult:
    """
    Erweiterte Validierung mit detaillierten Informationen für Debugging.
    
    Gibt zusätzliche Informationen zurück für:
    - Audit-Trail
    - Fehleranalyse
    - Metriken-Erfassung
    
    Args:
        output: Der zu validierende Output
        retry_count: Aktuelle Retry-Anzahl
        schema_version: Schema-Version
    
    Returns:
        TaskValidationResult mit allen Details
    """
    result = validate_task_result(output, retry_count, schema_version)
    
    # Füge detaillierte Informationen hinzu
    if result.error_type in [ValidationErrorType.PARSING, ValidationErrorType.SEMANTIC]:
        # Schema-Fehlerdetails
        result.validation_passes["schema_errors"] = get_schema_errors_detailed(output, schema_version)
        
        # Semantische Details
        if "data" in dir():
            result.validation_passes["semantic_details"] = get_semantic_validation_details(data)
    
    return result


def get_validation_prompt_enhancement(error_type: str, result: TaskValidationResult) -> Optional[str]:
    """
    Gibt eine Prompt-Verbesserung basierend auf dem Fehlertyp zurück.
    
    REQ-VAL-005: Differenzierte Retry-Logik
    
    Args:
        error_type: Der Fehlertyp
        result: Das Validierungsergebnis
    
    Returns:
        Eine verbesserte Prompt-Anleitung oder None
    """
    if error_type == ValidationErrorType.PARSING:
        policy = get_retry_policy(ValidationErrorType.PARSING)
        return policy.prompt_enhancement
    
    elif error_type == ValidationErrorType.SEMANTIC:
        policy = get_retry_policy(ValidationErrorType.SEMANTIC)
        return policy.prompt_enhancement
    
    return None
