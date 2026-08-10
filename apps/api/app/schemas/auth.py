from pydantic import BaseModel, ConfigDict


class DevPersonaOut(BaseModel):
    persona_key: str
    full_name: str
    title: str | None
    platform_role: str
    module_roles: list[dict]
    avatar_color: str | None


class DevLoginRequest(BaseModel):
    persona_key: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "CurrentUserOut"


class CurrentUserOut(BaseModel):
    id: int
    email: str
    full_name: str
    title: str | None
    platform_role: str
    avatar_color: str | None
    module_roles: list[dict]

    model_config = ConfigDict(from_attributes=True)
