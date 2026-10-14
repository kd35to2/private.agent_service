from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, SecretStr, StringConstraints

Username = Annotated[
    str,
    BeforeValidator(lambda value: value.strip().lower() if isinstance(value, str) else value),
    StringConstraints(pattern=r"^[a-z0-9_.-]{3,32}$"),
]
Password = Annotated[SecretStr, Field(min_length=8, max_length=128)]


class Credentials(BaseModel):
    username: Username
    password: Password


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    created_at: datetime


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class ChangePasswordInput(BaseModel):
    current_password: Password
    new_password: Password
