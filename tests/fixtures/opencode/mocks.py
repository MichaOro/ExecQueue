"""OpenCode mock fixtures for contract testing."""

from __future__ import annotations

# Health endpoint mock responses
HEALTH_RESPONSE_OK = {
    "status": "ok",
    "version": "0.1.0",
}

HEALTH_RESPONSE_ERROR = {
    "status": "error",
    "message": "Database connection failed",
}

# Session creation mock responses
SESSION_CREATE_REQUEST = {
    "name": "test-session",
}

SESSION_CREATE_RESPONSE = {
    "id": "sess_abc123def456",
    "name": "test-session",
    "created_at": "2024-01-15T10:30:00Z",
}

SESSION_CREATE_RESPONSE_NO_NAME = {
    "id": "sess_xyz789ghi012",
    "created_at": "2024-01-15T10:31:00Z",
}

# Message dispatch mock responses
MESSAGE_DISPATCH_REQUEST = {
    "content": "Explain quantum computing in simple terms.",
    "role": "user",
}

MESSAGE_DISPATCH_RESPONSE = {
    "id": "msg_qwe456rty789",
    "session_id": "sess_abc123def456",
    "status": "processing",
    "created_at": "2024-01-15T10:32:00Z",
}

# Message polling mock responses
MESSAGE_POLLING_RESPONSE_PENDING = {
    "id": "msg_qwe456rty789",
    "session_id": "sess_abc123def456",
    "status": "processing",
    "created_at": "2024-01-15T10:32:00Z",
}

MESSAGE_POLLING_RESPONSE_COMPLETED = {
    "id": "msg_qwe456rty789",
    "session_id": "sess_abc123def456",
    "status": "completed",
    "content": "Quantum computing uses quantum mechanics to process information...",
    "created_at": "2024-01-15T10:32:00Z",
    "completed_at": "2024-01-15T10:32:15Z",
}

MESSAGE_POLLING_RESPONSE_FAILED = {
    "id": "msg_qwe456rty789",
    "session_id": "sess_abc123def456",
    "status": "failed",
    "error": "Model inference failed: timeout",
    "created_at": "2024-01-15T10:32:00Z",
}

# SSE event stream mock responses
SSE_EVENTS_SEQUENCE = [
    # Event 1: message.started
    {
        "raw": "event: message.started\ndata: {\"id\": \"msg_qwe456rty789\", \"session_id\": \"sess_abc123def456\", \"status\": \"processing\"}\n\n",
        "parsed": {
            "event_type": "message.started",
            "data": {
                "id": "msg_qwe456rty789",
                "session_id": "sess_abc123def456",
                "status": "processing",
            },
        },
    },
    # Event 2: message.delta (first chunk)
    {
        "raw": "event: message.delta\ndata: {\"id\": \"msg_qwe456rty789\", \"content\": \"Quant\"}\n\n",
        "parsed": {
            "event_type": "message.delta",
            "data": {
                "id": "msg_qwe456rty789",
                "content": "Quant",
            },
        },
    },
    # Event 3: message.delta (second chunk)
    {
        "raw": "event: message.delta\ndata: {\"id\": \"msg_qwe456rty789\", \"content\": \"um computing\"}\n\n",
        "parsed": {
            "event_type": "message.delta",
            "data": {
                "id": "msg_qwe456rty789",
                "content": "um computing",
            },
        },
    },
    # Event 4: message.delta (final chunk)
    {
        "raw": "event: message.delta\ndata: {\"id\": \"msg_qwe456rty789\", \"content\": \" uses quantum mechanics\"}\n\n",
        "parsed": {
            "event_type": "message.delta",
            "data": {
                "id": "msg_qwe456rty789",
                "content": " uses quantum mechanics",
            },
        },
    },
    # Event 5: message.completed
    {
        "raw": "event: message.completed\ndata: {\"id\": \"msg_qwe456rty789\", \"session_id\": \"sess_abc123def456\", \"status\": \"completed\", \"content\": \"Quantum computing uses quantum mechanics...\"}\n\n",
        "parsed": {
            "event_type": "message.completed",
            "data": {
                "id": "msg_qwe456rty789",
                "session_id": "sess_abc123def456",
                "status": "completed",
                "content": "Quantum computing uses quantum mechanics...",
            },
        },
    },
]

SSE_HEARTBEAT_EVENT = {
    "raw": "event: heartbeat\ndata: {\"ts\": \"2024-01-15T10:32:30Z\"}\n\n",
    "parsed": {
        "event_type": "heartbeat",
        "data": {"ts": "2024-01-15T10:32:30Z"},
    },
}

SSE_ERROR_EVENT = {
    "raw": "event: message.failed\ndata: {\"id\": \"msg_qwe456rty789\", \"error\": \"Model unavailable\"}\n\n",
    "parsed": {
        "event_type": "message.failed",
        "data": {
            "id": "msg_qwe456rty789",
            "error": "Model unavailable",
        },
    },
}

# Error responses
ERROR_404_SESSION_NOT_FOUND = {
    "error": "Session not found",
    "message": "Session sess_invalid does not exist",
}

ERROR_400_INVALID_REQUEST = {
    "error": "Bad Request",
    "message": "Missing required field: content",
}

ERROR_500_INTERNAL = {
    "error": "Internal Server Error",
    "message": "An unexpected error occurred",
}

# HTTP status codes
STATUS_OK = 200
STATUS_CREATED = 201
STATUS_ACCEPTED = 202
STATUS_BAD_REQUEST = 400
STATUS_NOT_FOUND = 404
STATUS_INTERNAL_ERROR = 500

# Endpoint paths (assumed - may vary in actual implementation)
ENDPOINTS = {
    "health": "/health",
    "sessions": "/sessions",
    "session_messages": "/sessions/{session_id}/messages",
    "session_message": "/sessions/{session_id}/messages/{message_id}",
    "events": "/event",
}

# Alternative endpoint paths (implementation risks)
ALTERNATIVE_ENDPOINTS = {
    "session_messages": "/sessions/{session_id}/run",
    "events": "/sessions/{session_id}/events",
}
