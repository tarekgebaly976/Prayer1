from fastapi import HTTPException, status


class DomainError(Exception):
    """Business-rule violation; mapped to HTTP 409/422 by the API layer."""

    def __init__(self, message: str, code: str = "domain_error", status_code: int = 409):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def not_found(what: str = "Resource") -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


def forbidden(msg: str = "Not permitted") -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, msg)
