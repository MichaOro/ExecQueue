"""
Schema-Validator für Task-Validierung.

Bietet JSON-Schema-Validierung für Task-Ausgaben mit versionierbaren Schemata.
Erfüllt REQ-VAL-001 (JSON Schema Enforcement) und REQ-VAL-002 (Parsing Robustheit).
"""

import json
import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple

import jsonschema
from jsonschema import validate, ValidationError, Draft7Validator

logger = logging.getLogger(__name__)


class SchemaValidationError(Exception):
    """Custom exception for schema validation errors."""
    def __init__(self, message: str, errors: List[str]):
        super().__init__(message)
        self.errors = errors


def extract_json_from_output(output: str) -> Optional[str]:
    """
    Extrahiert JSON aus dem Output, unterstützt:
    - Reines JSON
    - JSON innerhalb von Markdown Code-Blöcken (```json ... ```)
    - JSON innerhalb von ``` ... ``` Blöcken
    
    REQ-VAL-002: Output Parsing Robustheit
    """
    if not output or not output.strip():
        return None
    
    output_stripped = output.strip()
    
    # Versuch 1: Reines JSON parsen
    try:
        json.loads(output_stripped)
        return output_stripped
    except json.JSONDecodeError:
        pass
    
    # Versuch 2: JSON in Markdown Code-Blöcken
    # Muster für ```json ... ``` oder ``` ... ```
    markdown_pattern = r'```(?:json)?\s*\n?(.*?)\n?```'
    matches = re.findall(markdown_pattern, output_stripped, re.DOTALL | re.IGNORECASE)
    
    if matches:
        # Nehmen den ersten Code-Block
        json_candidate = matches[0].strip()
        try:
            json.loads(json_candidate)
            return json_candidate
        except json.JSONDecodeError:
            logger.debug(f"JSON in Markdown-Block nicht valide: {json_candidate[:100]}...")
    
    # Versuch 3: Suche nach { ... } im gesamten Text (robuster Fallback)
    brace_pattern = r'\{[^{}]*\}'
    matches = re.findall(brace_pattern, output_stripped, re.DOTALL)
    
    for match in matches:
        try:
            json.loads(match)
            return match
        except json.JSONDecodeError:
            continue
    
    # Kein valides JSON gefunden
    return None


def load_schema(schema_version: str = "1.0.0") -> dict:
    """
    Lädt das JSON-Schema für die Validierung.
    
    Args:
        schema_version: Version des Schemas (z.B. "1.0.0")
    
    Returns:
        Das JSON-Schema als Dictionary
    """
    # Schema-Pfad basierend auf Version
    schema_dir = Path(__file__).parent / "schema"
    schema_file = schema_dir / f"{schema_version.replace('.', '_')}.json"
    
    # Fallback auf v1.json wenn spezifische Version nicht gefunden
    if not schema_file.exists():
        schema_file = schema_dir / "v1.json"
    
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema-Datei nicht gefunden: {schema_file}")
    
    with open(schema_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def validate_schema(output: str, schema_version: str = "1.0.0") -> Tuple[bool, List[str]]:
    """
    Validiert den Output gegen das JSON-Schema.
    
    REQ-VAL-001: JSON Schema Enforcement
    REQ-VAL-002: Output Parsing Robustheit
    
    Args:
        output: Der zu validierende Output-String (JSON oder Markdown-wrapped)
        schema_version: Version des zu verwendenden Schemas
    
    Returns:
        Tuple aus (ist_valide, Liste von Fehlermeldungen)
        - Bei Erfolg: (True, [])
        - Bei Fehler: (False, [fehlerbeschreibung1, fehlerbeschreibung2, ...])
    
    Raises:
        SchemaValidationError: Bei kritischen Fehlern beim Laden des Schemas
    """
    errors: List[str] = []
    
    # Schritt 1: JSON extrahieren (mit Markdown-Support)
    json_str = extract_json_from_output(output)
    
    if json_str is None:
        return False, ["Kein valider JSON-Inhalt im Output gefunden"]
    
    # Schritt 2: JSON parsen
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        return False, [f"JSON-Parsing fehlgeschlagen: {str(e)}"]
    
    # Schritt 3: Prüfen ob es ein Dictionary ist
    if not isinstance(data, dict):
        return False, ["JSON-Root muss ein Objekt (Dictionary) sein"]
    
    # Schritt 4: Schema laden
    try:
        schema = load_schema(schema_version)
    except FileNotFoundError as e:
        logger.error(f"Schema nicht gefunden: {e}")
        raise SchemaValidationError("Schema nicht gefunden", [str(e)])
    
    # Schritt 5: Validierung gegen Schema
    try:
        validate(instance=data, schema=schema)
        return True, []
    except ValidationError as e:
        # Sammle alle Validierungsfehler
        error_messages = []
        
        # Hauptfehler
        error_messages.append(f"Schema-Fehler: {e.message}")
        
        # Pfad zum Fehler
        if e.absolute_path:
            path = " -> ".join(str(p) for p in e.absolute_path)
            error_messages.append(f"Pfad: {path}")
        
        # Bei verschachtelten Fehlern alle sammeln
        for sub_error in e.context:
            error_messages.append(f"Unterfehler: {sub_error.message}")
        
        return False, error_messages


def get_schema_errors_detailed(output: str, schema_version: str = "1.0.0") -> List[dict]:
    """
    Gibt detaillierte Fehlerinformationen zurück für besseres Debugging.
    
    Args:
        output: Der zu validierende Output
        schema_version: Schema-Version
    
    Returns:
        Liste von Fehler-Dicts mit Struktur:
        {
            "type": "parsing" | "schema",
            "message": "Fehlerbeschreibung",
            "path": "Feldpfad (falls zutreffend)",
            "context": "Zusätzliche Informationen"
        }
    """
    errors = []
    
    # JSON extrahieren
    json_str = extract_json_from_output(output)
    
    if json_str is None:
        return [{
            "type": "parsing",
            "message": "Kein valider JSON-Inhalt gefunden",
            "path": None,
            "context": "Output enthält kein JSON oder kein extrahierbares JSON"
        }]
    
    # JSON parsen
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        return [{
            "type": "parsing",
            "message": f"JSON-Parsing-Fehler: {str(e)}",
            "path": None,
            "context": {"raw_output": output[:200]}
        }]
    
    if not isinstance(data, dict):
        return [{
            "type": "schema",
            "message": "JSON-Root muss ein Objekt sein",
            "path": None,
            "context": {"got_type": type(data).__name__}
        }]
    
    # Schema laden und validieren
    try:
        schema = load_schema(schema_version)
    except FileNotFoundError:
        return [{
            "type": "schema",
            "message": "Schema-Datei nicht gefunden",
            "path": None,
            "context": {"version": schema_version}
        }]
    
    validator = Draft7Validator(schema)
    validation_errors = list(validator.iter_errors(data))
    
    for error in validation_errors:
        errors.append({
            "type": "schema",
            "message": error.message,
            "path": " -> ".join(str(p) for p in error.absolute_path) if error.absolute_path else None,
            "context": {
                "schema_path": " -> ".join(str(p) for p in error.schema_path) if error.schema_path else None,
                "instance": str(error.instance)[:100] if error.instance else None
            }
        })
    
    return errors
