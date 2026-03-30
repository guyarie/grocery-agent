"""
API logging utilities for external service calls.

Provides structured logging for external API requests and responses
with automatic sensitive data redaction.
"""

import logging
import time
import re
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def redact_sensitive_data(data: Any, redact_keys: Optional[list] = None) -> Any:
    """
    Recursively redact sensitive data from dictionaries and strings.
    
    Args:
        data: Data to redact (dict, list, str, or other)
        redact_keys: List of keys to redact (case-insensitive)
        
    Returns:
        Data with sensitive values redacted
    """
    if redact_keys is None:
        redact_keys = [
            'authorization', 'token', 'access_token', 'refresh_token',
            'api_key', 'apikey', 'api-key', 'password', 'secret',
            'client_secret', 'bearer'
        ]
    
    # Convert keys to lowercase for comparison
    redact_keys_lower = [k.lower() for k in redact_keys]
    
    if isinstance(data, dict):
        redacted = {}
        for key, value in data.items():
            if key.lower() in redact_keys_lower:
                redacted[key] = '***REDACTED***'
            else:
                redacted[key] = redact_sensitive_data(value, redact_keys)
        return redacted
    
    elif isinstance(data, list):
        return [redact_sensitive_data(item, redact_keys) for item in data]
    
    elif isinstance(data, str):
        # Redact bearer tokens in strings
        data = re.sub(
            r'Bearer\s+[A-Za-z0-9\-._~+/]+=*',
            'Bearer ***REDACTED***',
            data,
            flags=re.IGNORECASE
        )
        # Redact API keys in strings
        data = re.sub(
            r'(api[_-]?key|apikey)["\s:=]+[A-Za-z0-9\-._~+/]+',
            r'\1=***REDACTED***',
            data,
            flags=re.IGNORECASE
        )
        return data
    
    else:
        return data


def log_api_request(
    api_name: str,
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Any] = None,
    request_id: Optional[str] = None
) -> float:
    """
    Log an external API request with sensitive data redaction.
    
    Args:
        api_name: Name of the API (e.g., 'Kroger', 'Gemini')
        method: HTTP method (GET, POST, PUT, etc.)
        url: Request URL
        headers: Request headers
        params: Query parameters
        body: Request body
        request_id: Optional request ID for tracing
        
    Returns:
        Start time (for calculating duration)
    """
    start_time = time.time()
    
    # Redact sensitive data
    safe_headers = redact_sensitive_data(headers) if headers else {}
    safe_params = redact_sensitive_data(params) if params else {}
    safe_body = redact_sensitive_data(body) if body else None
    
    # Build log message
    log_parts = [
        f"{api_name} API Request:",
        f"method={method}",
        f"url={url}"
    ]
    
    if request_id:
        log_parts.append(f"request_id={request_id}")
    
    log_message = " ".join(log_parts)
    
    logger.info(log_message)
    
    # Log details at debug level
    if safe_headers:
        logger.debug(f"{api_name} API Request Headers: {safe_headers}")
    if safe_params:
        logger.debug(f"{api_name} API Request Params: {safe_params}")
    if safe_body:
        # Truncate large bodies
        body_str = str(safe_body)
        if len(body_str) > 500:
            body_str = body_str[:500] + "... (truncated)"
        logger.debug(f"{api_name} API Request Body: {body_str}")
    
    return start_time


def log_api_response(
    api_name: str,
    status_code: int,
    response_body: Optional[Any] = None,
    start_time: Optional[float] = None,
    request_id: Optional[str] = None,
    error: Optional[str] = None
):
    """
    Log an external API response with sensitive data redaction.
    
    Args:
        api_name: Name of the API (e.g., 'Kroger', 'Gemini')
        status_code: HTTP status code
        response_body: Response body
        start_time: Request start time (for duration calculation)
        request_id: Optional request ID for tracing
        error: Optional error message
    """
    # Calculate duration
    duration = time.time() - start_time if start_time else None
    
    # Redact sensitive data from response
    safe_response = redact_sensitive_data(response_body) if response_body else None
    
    # Build log message
    log_parts = [
        f"{api_name} API Response:",
        f"status={status_code}"
    ]
    
    if duration is not None:
        log_parts.append(f"duration={duration:.3f}s")
    
    if request_id:
        log_parts.append(f"request_id={request_id}")
    
    log_message = " ".join(log_parts)
    
    # Log at appropriate level
    if status_code >= 500:
        logger.error(log_message)
    elif status_code >= 400:
        logger.warning(log_message)
    else:
        logger.info(log_message)
    
    # Log error details if present
    if error:
        logger.error(f"{api_name} API Error: {error}")
    
    # Log response body at debug level
    if safe_response:
        response_str = str(safe_response)
        if len(response_str) > 1000:
            response_str = response_str[:1000] + "... (truncated)"
        logger.debug(f"{api_name} API Response Body: {response_str}")


def log_api_error(
    api_name: str,
    error: Exception,
    method: Optional[str] = None,
    url: Optional[str] = None,
    request_id: Optional[str] = None
):
    """
    Log an external API error.
    
    Args:
        api_name: Name of the API (e.g., 'Kroger', 'Gemini')
        error: Exception that occurred
        method: HTTP method
        url: Request URL
        request_id: Optional request ID for tracing
    """
    log_parts = [
        f"{api_name} API Error:",
        f"error={type(error).__name__}: {str(error)}"
    ]
    
    if method and url:
        log_parts.append(f"request={method} {url}")
    
    if request_id:
        log_parts.append(f"request_id={request_id}")
    
    log_message = " ".join(log_parts)
    
    logger.error(log_message, exc_info=True)
