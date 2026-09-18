from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ValidationFailed(AppError):
    def __init__(self, message: str):
        super().__init__("VALIDATION_ERROR", message, status_code=400)


class NeedsClarification(Exception):
    def __init__(self, message: str, missing_fields: list[str] | None = None):
        self.message = message
        self.missing_fields = missing_fields or []
        super().__init__(message)


def error_body(code: str, message: str) -> dict:
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
        },
    }


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message),
    )


async def clarification_handler(_request: Request, exc: NeedsClarification) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "success": False,
            "status": "needs_clarification",
            "message": exc.message,
            "missing_fields": exc.missing_fields,
            "error": {
                "code": "NEEDS_CLARIFICATION",
                "message": exc.message,
            },
        },
    )


async def request_validation_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    missing = []
    messages = []
    for err in exc.errors():
        loc = [str(part) for part in err.get("loc", []) if part != "body"]
        field = loc[-1] if loc else "request"
        if err.get("type") == "missing":
            missing.append(field)
        messages.append(err.get("msg", "Invalid request"))

    if missing and all(
        err.get("type") == "missing" for err in exc.errors() if err.get("type")
    ):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "status": "needs_clarification",
                "message": "Required information is missing.",
                "missing_fields": missing,
                "error": {
                    "code": "NEEDS_CLARIFICATION",
                    "message": "Required information is missing.",
                },
            },
        )

    return JSONResponse(
        status_code=400,
        content=error_body(
            "VALIDATION_ERROR",
            messages[0] if messages else "Invalid request.",
        ),
    )
