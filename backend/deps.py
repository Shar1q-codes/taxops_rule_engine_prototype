from __future__ import annotations

import os
from typing import NamedTuple, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.db_models import FirmMembershipORM, FirmORM, UserORM
from backend.security import decode_token, hash_password

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


class RequestContext(NamedTuple):
    user: UserORM
    firm: FirmORM
    membership: Optional[FirmMembershipORM]


def _ensure_demo_user_and_firm(db: Session) -> RequestContext:
    firm = db.query(FirmORM).filter(FirmORM.name == "Demo CPA Firm").first()
    if not firm:
        firm = FirmORM(id="demo-firm", name="Demo CPA Firm", slug="demo-firm")
        db.add(firm)
        db.flush()

    user = db.query(UserORM).filter(UserORM.email == "demo@taxops.local").first()
    if not user:
        user = UserORM(
            id="demo-user",
            email="demo@taxops.local",
            hashed_password=hash_password("password"),
            full_name="Demo User",
            is_active=1,
            is_superuser=1,
        )
        db.add(user)
        db.flush()

    membership = (
        db.query(FirmMembershipORM)
        .filter(FirmMembershipORM.user_id == user.id, FirmMembershipORM.firm_id == firm.id)
        .first()
    )
    if not membership:
        membership = FirmMembershipORM(user_id=user.id, firm_id=firm.id, role="owner")
        db.add(membership)
    db.commit()
    return RequestContext(user=user, firm=firm, membership=membership)


def get_token_payload(token: Optional[str] = Depends(oauth2_scheme)) -> dict:
    auth_bypass = os.getenv("AUTH_BYPASS", "false").lower() == "true"
    if auth_bypass:
        return {"sub": "demo-user", "firm_id": "demo-firm"}
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return payload


def get_current_user(
    payload: dict = Depends(get_token_payload),
    db: Session = Depends(get_db),
) -> UserORM:
    auth_bypass = os.getenv("AUTH_BYPASS", "false").lower() == "true"
    if auth_bypass:
        return _ensure_demo_user_and_firm(db).user

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")
    user = db.query(UserORM).filter(UserORM.id == sub).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive or missing user.")
    return user


def get_current_firm(
    payload: dict = Depends(get_token_payload),
    db: Session = Depends(get_db),
    user: UserORM = Depends(get_current_user),
) -> FirmORM:
    auth_bypass = os.getenv("AUTH_BYPASS", "false").lower() == "true"
    if auth_bypass:
        return _ensure_demo_user_and_firm(db).firm

    firm_id = payload.get("firm_id")
    if not firm_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing firm in token.")
    firm = db.query(FirmORM).filter(FirmORM.id == firm_id).first()
    if not firm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Firm not found.")
    membership = (
        db.query(FirmMembershipORM)
        .filter(FirmMembershipORM.user_id == user.id, FirmMembershipORM.firm_id == firm.id)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not part of this firm.")
    return firm


def get_current_context(
    user: UserORM = Depends(get_current_user),
    firm: FirmORM = Depends(get_current_firm),
    db: Session = Depends(get_db),
) -> RequestContext:
    auth_bypass = os.getenv("AUTH_BYPASS", "false").lower() == "true"
    membership = None
    if auth_bypass:
        membership = _ensure_demo_user_and_firm(db).membership
    else:
        membership = (
            db.query(FirmMembershipORM)
            .filter(FirmMembershipORM.user_id == user.id, FirmMembershipORM.firm_id == firm.id)
            .first()
        )
    return RequestContext(user=user, firm=firm, membership=membership)
