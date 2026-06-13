class OpexError(Exception):
    pass


class DataGenerationError(OpexError):
    pass


class ValidationError(OpexError):
    pass


class ReportError(OpexError):
    pass


class DashboardError(OpexError):
    pass
