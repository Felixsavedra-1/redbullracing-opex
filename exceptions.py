class OpexError(Exception):
    """Base exception for all OPEX pipeline errors."""


class DataGenerationError(OpexError):
    """Raised when synthetic data generation fails due to invalid parameters."""


class ValidationError(OpexError):
    """Raised when input data fails schema or value validation."""


class ReportError(OpexError):
    """Raised when Excel report generation fails."""


class DashboardError(OpexError):
    """Raised when the interactive HTML dashboard fails to build or write."""
