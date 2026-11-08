from pydantic import BaseModel


class AtworkMeOut(BaseModel):
    """The caller's identity and DijiAtWork access, from verified claims only."""

    user_id: int
    full_name: str
    module_access: bool
    role: str | None
    permissions: list[str]
