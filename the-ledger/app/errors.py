"""A consistent JSON error shape for the whole API.

Every error is ``{"error": {"code": ..., "message": ..., "detail": ...}}``.
Messages are deliberately informative enough to teach the lifecycle but never
to hand over the solution.
"""
from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, detail=None):
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message
        self.detail = detail


def error_body(code: str, message: str, detail=None):
    body = {"error": {"code": code, "message": message}}
    if detail is not None:
        body["error"]["detail"] = detail
    return body


def install_handlers(app):
    @app.exception_handler(ApiError)
    def _api_error(_: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, exc.detail),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(HTTPException)
    def _http_error(_: Request, exc: HTTPException):
        code = {
            401: "unauthenticated",
            403: "forbidden",
            404: "not_found",
            409: "conflict",
        }.get(exc.status_code, "error")
        message = exc.detail if isinstance(exc.detail, str) else "request failed"
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(code, message),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    def _validation_error(_: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_body(
                "validation_error",
                "the request body did not match the expected schema",
                exc.errors(),
            ),
        )
