import datetime
import logging
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext

from metoxes.config import config
from metoxes.database import database, user_table


logger = logging.getLogger(__name__)

ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)


def create_unauthorized_exception(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def access_token_expire_minutes() -> int:
    return 30


def confirm_token_expire_minutes() -> int:
    return 1440


def get_secret_key() -> str:
    if not config.SECRET_KEY:
        raise RuntimeError("SECRET_KEY environment variable is missing")

    return config.SECRET_KEY


def create_access_token(email: str) -> str:
    logger.debug(
        "Creating access token",
        extra={"email": email},
    )

    expire = (
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(
            minutes=access_token_expire_minutes()
        )
    )

    jwt_data = {
        "sub": email,
        "exp": expire,
        "type": "access",
    }

    return jwt.encode(
        jwt_data,
        key=get_secret_key(),
        algorithm=ALGORITHM,
    )


def create_confirmation_token(email: str) -> str:
    logger.debug(
        "Creating confirmation token",
        extra={"email": email},
    )

    expire = (
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(
            minutes=confirm_token_expire_minutes()
        )
    )

    jwt_data = {
        "sub": email,
        "exp": expire,
        "type": "confirmation",
    }

    return jwt.encode(
        jwt_data,
        key=get_secret_key(),
        algorithm=ALGORITHM,
    )


def get_subject_for_token_type(
    token: str,
    token_type: Literal["access", "confirmation"],
) -> str:
    try:
        payload = jwt.decode(
            token,
            key=get_secret_key(),
            algorithms=[ALGORITHM],
        )

    except ExpiredSignatureError as exc:
        raise create_unauthorized_exception(
            "Token has expired"
        ) from exc

    except JWTError as exc:
        raise create_unauthorized_exception(
            "Invalid token"
        ) from exc

    email = payload.get("sub")

    if email is None:
        raise create_unauthorized_exception(
            "Token is missing 'sub' field"
        )

    payload_token_type = payload.get("type")

    if payload_token_type != token_type:
        raise create_unauthorized_exception(
            f"Token has incorrect type, expected '{token_type}'"
        )

    return email


def get_password_hash(password: str) -> str:
    if len(password.encode("utf-8")) > 72:
        raise ValueError(
            "Password must not exceed 72 bytes"
        )

    return pwd_context.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    if len(plain_password.encode("utf-8")) > 72:
        return False

    return pwd_context.verify(
        plain_password,
        hashed_password,
    )


async def get_user(email: str):
    logger.debug(
        "Fetching user from the database",
        extra={"email": email},
    )

    query = user_table.select().where(
        user_table.c.email == email
    )

    return await database.fetch_one(query)


async def authenticate_user(
    email: str,
    password: str,
):
    logger.debug(
        "Authenticating user",
        extra={"email": email},
    )

    user = await get_user(email)

    if not user:
        raise create_unauthorized_exception(
            "Invalid email or password"
        )

    if not verify_password(
        password,
        user.password,
    ):
        raise create_unauthorized_exception(
            "Invalid email or password"
        )

    if not user.confirmed:
        raise create_unauthorized_exception(
            "User has not confirmed email"
        )

    return user


async def get_current_user(
    token: Annotated[
        str,
        Depends(oauth2_scheme),
    ],
):
    email = get_subject_for_token_type(
        token,
        "access",
    )

    user = await get_user(email=email)

    if user is None:
        raise create_unauthorized_exception(
            "Could not find user for this token"
        )

    return user