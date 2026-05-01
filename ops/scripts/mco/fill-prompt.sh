#!/usr/bin/env bash
set -euo pipefail

# Prompt-Generator
# - fragt einen Zielpfad ab
# - fragt eine Vorlage 1-5 ab
# - sucht relativ zum Ausführungsort im Ordner "Vorlagen" die passende Vorlage
#   Beispiel: Auswahl 4 -> Vorlagen/04_*
# - ersetzt @INPUT_PATH und {{INPUT_PATH}} durch den normalisierten Pfad
# - schreibt das Ergebnis nach prompt.txt und überschreibt den alten Inhalt
# - verwendet eine Temp-Datei + atomaren Move, damit prompt.txt nach dem Schreiben
#   wieder sauber freigegeben ist

SCRIPT_NAME="$(basename "$0")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
TEMPLATE_DIR="$SCRIPT_DIR/Vorlagen"
OUTPUT_FILE="$SCRIPT_DIR/prompt.txt"
DOCS_ROOT="$PROJECT_ROOT/docs"
PATH_MODE=""
SELECTED_DOCS_PATH=""

cleanup() {
  local exit_code=$?
  if [[ -n "${TMP_FILE:-}" && -f "$TMP_FILE" ]]; then
    rm -f "$TMP_FILE" 2>/dev/null || true
  fi
  exit "$exit_code"
}
trap cleanup EXIT INT TERM

fail() {
  printf 'Fehler: %s\n' "$1" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Benötigtes Kommando nicht gefunden: $1"
}

move_with_retries() {
  local source_file="$1"
  local target_file="$2"
  local max_attempts="${3:-10}"
  local sleep_seconds="${4:-0.2}"
  local attempt

  for ((attempt = 1; attempt <= max_attempts; attempt++)); do
    if mv -f "$source_file" "$target_file" 2>/dev/null; then
      return 0
    fi

    # Kurzzeitige Datei-Locks z. B. durch Editor/Indexer abfedern.
    if (( attempt < max_attempts )); then
      sleep "$sleep_seconds"
    fi
  done

  return 1
}

normalize_input_path() {
  local raw="$1"

  # Windows-Backslashes in Slash umwandeln
  raw="${raw//\\//}"

  # führende/trailing Spaces entfernen
  raw="$(printf '%s' "$raw" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

  # führendes @ entfernen, falls versehentlich mit eingegeben
  raw="${raw#@}"

  # trailing Slash entfernen, danach exakt einen Slash setzen
  raw="${raw%/}"

  [[ -n "$raw" ]] || fail "Pfad darf nicht leer sein."

  printf '@%s/' "$raw"
}

path_to_docs_relative() {
  local absolute_path="$1"
  local relative_path

  case "$absolute_path" in
    "$DOCS_ROOT")
      relative_path="docs"
      ;;
    "$DOCS_ROOT"/*)
      relative_path="docs/${absolute_path#"$DOCS_ROOT"/}"
      ;;
    *)
      fail "Ausgewählter Pfad liegt nicht unter /docs: $absolute_path"
      ;;
  esac

  printf '%s' "$relative_path"
}

collect_entries() {
  local current_dir="$1"
  local include_files="$2"
  local entry

  MENU_ENTRIES=()
  MENU_LABELS=()

  shopt -s nullglob

  for entry in "$current_dir"/*; do
    [[ -d "$entry" ]] || continue
    MENU_ENTRIES+=("$entry")
    MENU_LABELS+=("[Ordner] $(basename "$entry")")
  done

  if [[ "$include_files" == "true" ]]; then
    for entry in "$current_dir"/*; do
      [[ -f "$entry" ]] || continue
      MENU_ENTRIES+=("$entry")
      MENU_LABELS+=("[Datei]  $(basename "$entry")")
    done
  fi

  shopt -u nullglob
}

print_navigation_menu() {
  local current_dir="$1"
  local allow_file_selection="$2"
  local allow_current_dir_selection="$3"
  local docs_relative
  local index

  docs_relative="$(path_to_docs_relative "$current_dir")"

  printf '\nAktueller Pfad: /%s\n' "$docs_relative"
  printf 'Verfügbar:\n'

  if (( ${#MENU_ENTRIES[@]} == 0 )); then
    printf '  (keine Untereinträge)\n'
  else
    for index in "${!MENU_ENTRIES[@]}"; do
      printf '  %d) %s\n' "$((index + 1))" "${MENU_LABELS[$index]}"
    done
  fi

  if [[ "$allow_current_dir_selection" == "true" ]]; then
    printf '  0) Diesen Ordner verwenden\n'
  fi

  if [[ "$current_dir" != "$DOCS_ROOT" ]]; then
    printf '  u) Eine Ebene nach oben\n'
  fi

  if [[ "$allow_file_selection" == "true" ]]; then
    printf '  q) Abbrechen\n'
  else
    printf '  q) Abbrechen\n'
  fi
}

choose_path_mode() {
  local selection

  while true; do
    printf 'Was möchtest du verwenden?\n'
    printf '  1) Ordner\n'
    printf '  2) Datei\n'
    printf 'Auswahl (1-2): '
    IFS= read -r selection

    case "$selection" in
      1) PATH_MODE="directory"; return 0 ;;
      2) PATH_MODE="file"; return 0 ;;
      *) printf 'Bitte 1 oder 2 eingeben.\n\n' ;;
    esac
  done
}

choose_docs_path() {
  local mode="$1"
  local current_dir="$DOCS_ROOT"
  local allow_files="false"
  local allow_current_dir="false"
  local selection
  local selected_index
  local selected_path

  [[ -d "$DOCS_ROOT" ]] || fail "Docs-Ordner nicht gefunden: $DOCS_ROOT"

  if [[ "$mode" == "file" ]]; then
    allow_files="true"
  else
    allow_current_dir="true"
  fi

  while true; do
    collect_entries "$current_dir" "$allow_files"
    print_navigation_menu "$current_dir" "$allow_files" "$allow_current_dir"

    if [[ "$mode" == "directory" ]]; then
      printf 'Auswahl: '
    else
      printf 'Auswahl: '
    fi
    IFS= read -r selection

    case "$selection" in
      q|Q)
        fail "Auswahl abgebrochen."
        ;;
      u|U)
        if [[ "$current_dir" == "$DOCS_ROOT" ]]; then
          printf 'Du bist bereits im Wurzelordner /docs.\n'
        else
          current_dir="$(dirname "$current_dir")"
        fi
        ;;
      0)
        if [[ "$allow_current_dir" == "true" ]]; then
          SELECTED_DOCS_PATH="$(path_to_docs_relative "$current_dir")"
          return 0
        fi
        printf 'Diese Option ist hier nicht verfügbar.\n'
        ;;
      ''|*[!0-9]*)
        printf 'Bitte eine gültige Auswahl eingeben.\n'
        ;;
      *)
        selected_index=$((selection - 1))
        if (( selected_index < 0 || selected_index >= ${#MENU_ENTRIES[@]} )); then
          printf 'Bitte eine gültige Auswahl eingeben.\n'
          continue
        fi

        selected_path="${MENU_ENTRIES[$selected_index]}"

        if [[ -d "$selected_path" ]]; then
          current_dir="$selected_path"
          continue
        fi

        if [[ "$mode" == "file" && -f "$selected_path" ]]; then
          SELECTED_DOCS_PATH="$(path_to_docs_relative "$selected_path")"
          return 0
        fi

        printf 'Diese Auswahl kann hier nicht verwendet werden.\n'
        ;;
    esac
  done
}

select_template_file() {
  local selected_number="$1"
  local prefix
  prefix="$(printf '%02d' "$selected_number")"

  [[ -d "$TEMPLATE_DIR" ]] || fail "Vorlagen-Ordner nicht gefunden: $TEMPLATE_DIR"

  # Keine ls-Pipe verwenden, damit keine unnötigen Subshell-/Pipe-Nebenwirkungen entstehen.
  local matches=()
  shopt -s nullglob
  matches=("$TEMPLATE_DIR/${prefix}"*)
  shopt -u nullglob

  (( ${#matches[@]} > 0 )) || fail "Keine Vorlage mit Prefix ${prefix} im Ordner $TEMPLATE_DIR gefunden."
  (( ${#matches[@]} == 1 )) || fail "Mehrere Vorlagen mit Prefix ${prefix} gefunden. Bitte eindeutig benennen."

  [[ -f "${matches[0]}" ]] || fail "Gefundene Vorlage ist keine Datei: ${matches[0]}"

  printf '%s' "${matches[0]}"
}

replace_placeholders() {
  local template_file="$1"
  local replacement="$2"
  local tmp_file="$3"

  # Escape für sed replacement: &, \ und | müssen geschützt werden.
  local escaped_replacement
  escaped_replacement="$(printf '%s' "$replacement" | sed 's/[\\&|]/\\&/g')"

  # Ersetzt beide Platzhalter-Varianten, damit bestehende Vorlagen kompatibel bleiben.
  sed \
    -e "s|@INPUT_PATH|$escaped_replacement|g" \
    -e "s|{{INPUT_PATH}}|$escaped_replacement|g" \
    "$template_file" > "$tmp_file"
}

main() {
  require_command sed
  require_command mktemp
  require_command mv
  require_command sleep

  choose_path_mode
  choose_docs_path "$PATH_MODE"
  INPUT_PATH_RAW="$SELECTED_DOCS_PATH"
  NORMALIZED_INPUT_PATH="$(normalize_input_path "$INPUT_PATH_RAW")"

  printf 'Vorlage auswählen (1-5): '
  IFS= read -r TEMPLATE_SELECTION

  [[ "$TEMPLATE_SELECTION" =~ ^[1-5]$ ]] || fail "Vorlage muss eine Zahl von 1 bis 5 sein."

  TEMPLATE_FILE="$(select_template_file "$TEMPLATE_SELECTION")"

  TMP_FILE="$(mktemp "${OUTPUT_FILE}.tmp.XXXXXX")"

  # Template verarbeiten und in Temp-Datei schreiben
  if ! replace_placeholders "$TEMPLATE_FILE" "$NORMALIZED_INPUT_PATH" "$TMP_FILE"; then
    fail "Fehler beim Verarbeiten der Vorlage."
  fi

  # Vor dem Move prüfen, ob die Ausgabe-Datei beschreibbar ist
  if [[ -e "$OUTPUT_FILE" ]] && [[ ! -w "$OUTPUT_FILE" ]]; then
    # Versuchen, die Datei zu backupen und zu entfernen
    if move_with_retries "$OUTPUT_FILE" "${OUTPUT_FILE}.bak"; then
      printf 'Hinweis: Alte prompt.txt wurde zu prompt.txt.bak verschoben.\n' >&2
    else
      fail "Kann prompt.txt nicht überschreiben (Datei gesperrt?). Backup: ${OUTPUT_FILE}.bak"
    fi
  fi

  # Atomares Move mit Fehlerprüfung
  if ! move_with_retries "$TMP_FILE" "$OUTPUT_FILE"; then
    # Temp-Datei nicht leeren, damit Cleanup sie löschen kann
    fail "Fehler beim Schreiben von prompt.txt (Datei ggf. noch gesperrt oder Dateisystem-Problem)."
  fi
  TMP_FILE=""  # Cleanup-Trap darf jetzt nicht mehr löschen

  printf '\nFertig.\n'
  printf 'Vorlage: %s\n' "$TEMPLATE_FILE"
  printf 'Pfad: %s\n' "$NORMALIZED_INPUT_PATH"
  printf 'Ausgabe: %s\n' "$OUTPUT_FILE"
}

main "$@"
