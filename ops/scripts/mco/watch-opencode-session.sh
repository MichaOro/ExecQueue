#!/usr/bin/env bash
set -euo pipefail

: "${BASE_URL:=http://127.0.0.1:4096}"
: "${SESSION_ID:?SESSION_ID fehlt}"

NOW_MS="$(date +%s%3N)"

echo "--- SESSION STATUS ---"
curl -s "${BASE_URL}/session/status" | jq --arg sid "$SESSION_ID" '.[$sid]'

echo "--- SESSION META ---"
curl -s "${BASE_URL}/session/${SESSION_ID}" | jq '{slug, summary, updated: .time.updated}'

echo "--- MESSAGE SUMMARY ---"
curl -s "${BASE_URL}/session/${SESSION_ID}/message" | jq --argjson now "$NOW_MS" '
{
  message_count_total: length,
  assistant_messages: (map(select(.info.role == "assistant")) | length),
  user_messages: (map(select(.info.role == "user")) | length),
  unfinished_assistant_messages: (map(select(.info.role == "assistant" and (.info.finish // null) == null)) | length),
  last_message: (
    .[-1] | {
      id: .info.id,
      role: .info.role,
      finish: (.info.finish // null),
      created: .info.time.created,
      completed: (.info.time.completed // null),
      age_seconds: ((($now - (.info.time.created // $now)) / 1000) | floor),
      tokens: .info.tokens,
      part_types: [.parts[]?.type],
      has_text: any(.parts[]?; (.type == "text") and ((.text // "") | length > 0)),
      has_reasoning: any(.parts[]?; (.type == "reasoning") and ((.text // "") | length > 0)),
      has_tool: any(.parts[]?; .type == "tool")
    }
  )
}
'

echo "--- DIFF COUNT ---"
curl -s "${BASE_URL}/session/${SESSION_ID}/diff" | jq 'length'
