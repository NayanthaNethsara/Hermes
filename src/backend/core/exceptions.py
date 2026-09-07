from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ArchivistException(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class RetrievalThresholdError(ArchivistException):
    def __init__(self, message: str = "Retrieval confidence below required threshold") -> None:
        super().__init__(message=message, status_code=404)


class DocumentParsingError(ArchivistException):
    def __init__(self, message: str = "Document parsing and layout extraction failed") -> None:
        super().__init__(message=message, status_code=422)


class ModelInferenceError(ArchivistException):
    def __init__(self, message: str = "Language or vision model inference failure") -> None:
        super().__init__(message=message, status_code=502)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ArchivistException)
    async def handle_archivist_exception(
        request: Request, exc: ArchivistException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error_type": exc.__class__.__name__,
                "message": exc.message,
                "path": str(request.url.path),
            },
        )
