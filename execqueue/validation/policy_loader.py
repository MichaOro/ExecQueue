"""
Policy-Loader für Validation-Konfiguration.

Lädt und verwaltet die Validation-Policy aus policy.yaml.
Unterstützt Environment-spezifische Überschreibungen und Hot-Reload.

Erfüllt REQ-VAL-013 (Policy-Based Validation) und REQ-VAL-014 (Graceful Degradation).
"""

import logging
import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class RetryPolicy:
    """Retry-Policy für einen Fehlertyp."""
    max_retries: int
    base_backoff_seconds: int
    max_backoff_seconds: int
    jitter_percent: int
    description: str
    prompt_enhancement: Optional[str] = None
    auto_fail: bool = False


@dataclass
class ValidationConfig:
    """Globale Validierungs-Konfiguration."""
    evidence_min_length: int = 10
    evidence_required_for_done: bool = True
    strict_mode: bool = False
    schema_version: str = "1.0.0"


@dataclass
class EscalationConfig:
    """Eskalations-Konfiguration."""
    retry_threshold: int = 3
    manual_review_enabled: bool = True
    notification_enabled: bool = True
    notification_channels: list = field(default_factory=lambda: ["log"])
    webhook_url: str = ""


@dataclass
class Policy:
    """Gesamte Policy-Struktur."""
    validation: ValidationConfig
    retry_policies: Dict[str, RetryPolicy]
    escalation: EscalationConfig
    metrics_enabled: bool = True
    circuit_breaker_enabled: bool = False


# Singleton-Instanz
_policy_instance: Optional[Policy] = None


def _load_policy_from_file(policy_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Lädt die Policy aus der YAML-Datei.
    
    Args:
        policy_path: Pfad zur Policy-Datei (optional, Default: policy.yaml im validation-Verzeichnis)
    
    Returns:
        Das geladene Policy-Dictionary
    
    Raises:
        FileNotFoundError: Wenn die Policy-Datei nicht gefunden wird
        yaml.YAMLError: Bei Syntax-Fehlern in der YAML-Datei
    """
    if policy_path is None:
        # Default-Pfad: policy.yaml im validation-Verzeichnis
        policy_path = Path(__file__).parent / "policy.yaml"
    else:
        policy_path = Path(policy_path)
    
    if not policy_path.exists():
        raise FileNotFoundError(f"Policy-Datei nicht gefunden: {policy_path}")
    
    with open(policy_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def _apply_environment_overrides(policy: Dict[str, Any]) -> Dict[str, Any]:
    """
    Wendet Environment-spezifische Überschreibungen an.
    
    REQ-VAL-013: Policy-Based Validation (environment-specific thresholds)
    
    Args:
        policy: Das geladene Policy-Dictionary
    
    Returns:
        Das modifizierte Policy-Dictionary mit Environment-Overrides
    """
    # Environment ermitteln (PROD, DEV, TEST)
    env = os.getenv("EXECQUEUE_ENV", os.getenv("ENVIRONMENT", "development")).lower()
    
    # Test-Erkennung
    if os.getenv("EXECQUEUE_TEST_MODE", "").lower() == "true" or "pytest" in os.getenv("PYTEST_CURRENT_TEST", ""):
        env = "test"
    
    # Prüfen ob Overrides für dieses Environment existieren
    environments = policy.get("environments", {})
    if env not in environments:
        logger.info(f"Keine Environment-Overrides für '{env}', verwende Defaults")
        return policy
    
    overrides = environments[env]
    logger.info(f"Wende Environment-Overrides für '{env}' an")
    
    # Rekursive Merge-Funktion
    def deep_merge(base: Dict, override: Dict) -> Dict:
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    return deep_merge(policy, overrides)


def _parse_retry_policy(data: Dict[str, Any]) -> RetryPolicy:
    """Parsert ein Retry-Policy-Dictionary in ein RetryPolicy-Objekt."""
    return RetryPolicy(
        max_retries=data.get("max_retries", 3),
        base_backoff_seconds=data.get("base_backoff_seconds", 10),
        max_backoff_seconds=data.get("max_backoff_seconds", 120),
        jitter_percent=data.get("jitter_percent", 25),
        description=data.get("description", ""),
        prompt_enhancement=data.get("prompt_enhancement"),
        auto_fail=data.get("auto_fail", False),
    )


def _parse_validation_config(data: Dict[str, Any]) -> ValidationConfig:
    """Parsert ein Validation-Config-Dictionary."""
    return ValidationConfig(
        evidence_min_length=data.get("evidence_min_length", 10),
        evidence_required_for_done=data.get("evidence_required_for_done", True),
        strict_mode=data.get("strict_mode", False),
        schema_version=data.get("schema_version", "1.0.0"),
    )


def _parse_escalation_config(data: Dict[str, Any]) -> EscalationConfig:
    """Parsert ein Escalation-Config-Dictionary."""
    notification = data.get("notification", {})
    return EscalationConfig(
        retry_threshold=data.get("retry_threshold", 3),
        manual_review_enabled=data.get("manual_review_enabled", True),
        notification_enabled=notification.get("enabled", True),
        notification_channels=notification.get("channels", ["log"]),
        webhook_url=notification.get("webhook_url", ""),
    )


def load_policy(policy_path: Optional[str] = None, use_env_overrides: bool = True) -> Policy:
    """
    Lädt die Validation-Policy (Singleton).
    
    Args:
        policy_path: Optionaler Pfad zur Policy-Datei
        use_env_overrides: Ob Environment-Overrides angewendet werden sollen
    
    Returns:
        Das geladene Policy-Objekt
    """
    global _policy_instance
    
    try:
        raw_policy = _load_policy_from_file(policy_path)
        
        if use_env_overrides:
            raw_policy = _apply_environment_overrides(raw_policy)
        
        # Parsen in strukturierte Objekte
        policy = Policy(
            validation=_parse_validation_config(raw_policy.get("validation", {})),
            retry_policies={
                key: _parse_retry_policy(value)
                for key, value in raw_policy.get("retry_policies", {}).items()
            },
            escalation=_parse_escalation_config(raw_policy.get("escalation", {})),
            metrics_enabled=raw_policy.get("metrics", {}).get("enabled", True),
            circuit_breaker_enabled=raw_policy.get("circuit_breaker", {}).get("enabled", False),
        )
        
        _policy_instance = policy
        logger.info("Validation-Policy erfolgreich geladen")
        return policy
        
    except FileNotFoundError as e:
        logger.warning(f"Policy-Datei nicht gefunden: {e}. Verwende Defaults.")
        return get_default_policy()
    except yaml.YAMLError as e:
        logger.error(f"Syntax-Fehler in Policy-Datei: {e}. Verwende Defaults.")
        return get_default_policy()


def get_policy() -> Policy:
    """
    Gibt die aktuelle Policy zurück (Singleton).
    
    Lädt die Policy falls noch nicht geschehen.
    
    Returns:
        Das Policy-Objekt
    """
    global _policy_instance
    if _policy_instance is None:
        _policy_instance = load_policy()
    return _policy_instance


def reload_policy(policy_path: Optional[str] = None) -> Policy:
    """
    Lädt die Policy neu (für Hot-Reload).
    
    Args:
        policy_path: Optionaler Pfad zur Policy-Datei
    
    Returns:
        Das neu geladene Policy-Objekt
    """
    global _policy_instance
    _policy_instance = load_policy(policy_path)
    return _policy_instance


def get_default_policy() -> Policy:
    """
    Gibt eine Default-Policy zurück (Fallback bei Fehlern).
    
    Returns:
        Default Policy-Objekt
    """
    return Policy(
        validation=ValidationConfig(
            evidence_min_length=10,
            evidence_required_for_done=True,
            strict_mode=False,
            schema_version="1.0.0",
        ),
        retry_policies={
            "parsing": RetryPolicy(
                max_retries=3,
                base_backoff_seconds=5,
                max_backoff_seconds=60,
                jitter_percent=20,
                description="Parsing-Fehler",
            ),
            "semantic": RetryPolicy(
                max_retries=3,
                base_backoff_seconds=10,
                max_backoff_seconds=120,
                jitter_percent=25,
                description="Semantische Fehler",
            ),
            "critical": RetryPolicy(
                max_retries=0,
                base_backoff_seconds=0,
                max_backoff_seconds=0,
                jitter_percent=0,
                description="Kritische Fehler",
                auto_fail=True,
            ),
        },
        escalation=EscalationConfig(
            retry_threshold=3,
            manual_review_enabled=True,
            notification_enabled=True,
        ),
        metrics_enabled=True,
        circuit_breaker_enabled=False,
    )


def get_retry_policy(error_type: str) -> RetryPolicy:
    """
    Gibt die Retry-Policy für einen bestimmten Fehlertyp zurück.
    
    Args:
        error_type: Der Fehlertyp ("parsing", "semantic", "critical")
    
    Returns:
        Die entsprechende RetryPolicy
    """
    policy = get_policy()
    return policy.retry_policies.get(error_type, policy.retry_policies.get("critical"))


def calculate_backoff_seconds(
    error_type: str,
    retry_count: int,
    policy: Optional[Policy] = None
) -> float:
    """
    Berechnet das Backoff-Intervall mit exponentieller Verzögerung und Jitter.
    
    REQ-VAL-006: Exponential Backoff
    
    Formel: wait = min(base * 2^retry_count * (1 + jitter/100 * random()), max_backoff)
    
    Args:
        error_type: Der Fehlertyp
        retry_count: Aktuelle Retry-Anzahl (0-indexiert)
        policy: Optionales Policy-Objekt (wenn None, wird get_policy() verwendet)
    
    Returns:
        Das berechnete Backoff-Intervall in Sekunden
    """
    if policy is None:
        policy = get_policy()
    
    retry_policy = get_retry_policy(error_type)
    
    # Exponentielles Backoff
    base = retry_policy.base_backoff_seconds
    exponential_factor = 2 ** retry_count
    jitter_factor = 1 + (retry_policy.jitter_percent / 100) * random.random()
    
    backoff = base * exponential_factor * jitter_factor
    
    # Auf Maximalwert begrenzen
    backoff = min(backoff, retry_policy.max_backoff_seconds)
    
    return round(backoff, 2)


def should_retry(error_type: str, retry_count: int, policy: Optional[Policy] = None) -> bool:
    """
    Prüft ob ein Retry für den gegebenen Fehlertyp und die Retry-Anzahl möglich ist.
    
    Args:
        error_type: Der Fehlertyp
        retry_count: Aktuelle Retry-Anzahl
        policy: Optionales Policy-Objekt
    
    Returns:
        True wenn ein Retry möglich ist, False sonst
    """
    if policy is None:
        policy = get_policy()
    
    retry_policy = get_retry_policy(error_type)
    
    # Kritische Fehler haben keine Retries
    if retry_policy.auto_fail:
        return False
    
    return retry_count < retry_policy.max_retries


def should_escalate(error_type: str, retry_count: int, policy: Optional[Policy] = None) -> bool:
    """
    Prüft ob eine Eskalation erforderlich ist.
    
    Args:
        error_type: Der Fehlertyp
        retry_count: Aktuelle Retry-Anzahl
        policy: Optionales Policy-Objekt
    
    Returns:
        True wenn eskaliert werden sollte, False sonst
    """
    if policy is None:
        policy = get_policy()
    
    return retry_count >= policy.escalation.retry_threshold
