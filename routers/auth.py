from datetime import timedelta, datetime
from typing import Annotated

import starlette.status as status
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel

from config import config
from database.models import Users
from database.setup import db_dependency

router = APIRouter(prefix="/auth", tags=["auth"])
bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_bearer = OAuth2PasswordBearer(tokenUrl="auth/token")


class CreateUserRequest(BaseModel):
    username: str
    name: str
    email: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class UserLoginRequest(BaseModel):
    username: str
    password: str


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_user(db: db_dependency, create_user_request: CreateUserRequest):
    check_duplicate_username(db, create_user_request.username)
    create_user_model = Users(
        username=create_user_request.username,
        name=create_user_request.name,
        email=create_user_request.email,
        hashed_password=bcrypt_context.hash(create_user_request.password),
    )

    db.add(create_user_model)
    db.commit()
    return {"message": "User sucessfully created"}


@router.post("/login", response_model=Token)
async def login_for_access_token(
    form_data: UserLoginRequest, db: db_dependency
) -> dict:
    user = authenticate_user(form_data.username, form_data.password, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate user"
        )
    token = create_access_token(user.username, user.id, timedelta(minutes=60))

    return {
        "access_token": token,
        "token_type": "bearer",
    }


@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: db_dependency
) -> dict:
    user = authenticate_user(form_data.username, form_data.password, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate user"
        )
    token = create_access_token(user.username, user.id, timedelta(minutes=60))

    return {
        "access_token": token,
        "token_type": "bearer",
    }


def authenticate_user(username: str, password: str, db):
    user = db.query(Users).filter(Users.username == username).first()
    if not user:
        return False
    if not bcrypt_context.verify(password, user.hashed_password):
        return False
    return user


def create_access_token(username: str, user_id: int, expires_data: timedelta):
    encode = {"sub": username, "id": user_id}
    expire = datetime.utcnow() + expires_data
    encode.update({"exp": expire})
    return jwt.encode(encode, config.SECRET_KEY, algorithm=config.ALGORITHM)


def get_current_user(token: Annotated[str, Depends(oauth2_bearer)]) -> dict:
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])
        username: str = payload.get("sub")
        user_id: int = payload.get("id")
        if username is None or user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate user",
            )
        return {
            "username": username,
            "id": user_id,
        }
    except JWTError:
        HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate user"
        )


def check_duplicate_username(db, request_username):
    existing_user = db.query(Users).filter(Users.username == request_username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")
