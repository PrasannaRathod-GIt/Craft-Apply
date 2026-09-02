from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    username: str | None = None
    phone: str | None = None
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    username: str | None
    is_admin: bool

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    ok: bool = True
    message: str
    user: UserOut
