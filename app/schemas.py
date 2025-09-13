from pydantic import BaseModel


class UserOut(BaseModel):
    id: int
    name: str | None
    email: str | None
    provider: str


class Config:
    orm_mode = True