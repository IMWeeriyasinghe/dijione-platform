from fastapi import Request, status
from fastapi.responses import JSONResponse


class AttendanceError(Exception):
    """A rejected attendance action. ``detail`` is for people, ``code`` for clients."""

    def __init__(self, code: str, detail: str, status_code: int = status.HTTP_409_CONFLICT) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status_code = status_code


def attendance_error_handler(_request: Request, exc: AttendanceError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "code": exc.code})
