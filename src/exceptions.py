"""
Custom exception classes for the Agent Grocery application.
"""

class AgentGroceryException(Exception):
    """Base exception for all application errors."""
    pass

class ConfigurationError(AgentGroceryException):
    """Raised when configuration is invalid or missing."""
    pass

class KrogerAPIError(AgentGroceryException):
    """Raised when Kroger API operations fail."""
    pass

class ReceiptProcessingError(AgentGroceryException):
    """Raised when receipt processing fails."""
    pass

class VendorAPIError(AgentGroceryException):
    """Base class for vendor API errors."""
    pass

class MockDataWarning(UserWarning):
    """Warning raised when mock data is being used."""
    pass

class CSVError(AgentGroceryException):
    """Raised when CSV parsing or serialization fails."""
    pass

class LLMMatchingError(AgentGroceryException):
    """Raised when LLM matching operations fail."""
    pass