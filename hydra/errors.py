class HydraError(Exception):
    """Base error for the hydra package."""


class ContractError(HydraError):
    """Contract failed schema or slug checks."""


class AcquisitionError(HydraError):
    """Acquire failed. Classifier reads error_type and http_status."""

    def __init__(self, message, *, http_status=None, error_type="AcquisitionError"):
        super().__init__(message)
        self.http_status = http_status
        self.error_type = error_type


class ParseError(HydraError):
    """Extraction produced nothing usable."""


class SchemaError(HydraError):
    """One or more rows failed the contract schema."""

    def __init__(self, message, errors):
        super().__init__(message)
        self.errors = errors
