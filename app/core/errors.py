from fastapi import Request
from fastapi.responses import JSONResponse

class BusinessRuleValidationError(Exception):
    def __init__(self, message: str, code: str = "VALIDATION_ERROR"):
        self.message = message
        self.code = code

class NeedsClarificationError(Exception):
    def __init__(self, message: str, missing_fields: list):
        self.message = message
        self.missing_fields = missing_fields

async def business_validation_exception_handler(request: Request, exc: BusinessRuleValidationError):
    return JSONResponse(
        status_code=400,
        content={
            "success": False,
            "error": {
                "code": exc.code,
                "message": exc.message
            }
        }
    )

async def clarification_exception_handler(request: Request, exc: NeedsClarificationError):
    return JSONResponse(
        status_code=200,
        content={
            "success": False,
            "status": "needs_clarification",
            "message": exc.message,
            "missing_fields": exc.missing_fields
        }
    )