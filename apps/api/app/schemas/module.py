from pydantic import BaseModel, ConfigDict


class ModuleOut(BaseModel):
    id: int
    key: str
    name: str
    description: str
    icon: str
    route: str
    status: str
    enabled: bool
    display_order: int

    model_config = ConfigDict(from_attributes=True)
