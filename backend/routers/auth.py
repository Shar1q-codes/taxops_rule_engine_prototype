from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.db_models import FirmMembershipORM, FirmORM, UserORM
from backend.deps import RequestContext, get_current_context
from backend.schemas import FirmCreate, FirmRead, LoginRequest, MeAuthResponse, RegisterFirmRequest, Token, UserCreate, UserRead
from backend.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _ensure_email_unique(db: Session, email: str) -> None:
    existing = db.query(UserORM).filter(UserORM.email == email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already registered with this email.")


def _build_user_read(user: UserORM) -> UserRead:
    return UserRead(id=user.id, email=user.email, full_name=user.full_name, is_active=bool(user.is_active))


def _build_firm_read(firm: FirmORM) -> FirmRead:
    return FirmRead(id=firm.id, name=firm.name)


@router.post("/register-firm", response_model=Token)
def register_firm(payload: RegisterFirmRequest, db: Session = Depends(get_db)) -> Token:
    email = payload.user.email.lower()
    _ensure_email_unique(db, email)

    firm = FirmORM(name=payload.firm.name)
    db.add(firm)
    db.flush()

    user = UserORM(
        email=email,
        hashed_password=hash_password(payload.user.password),
        full_name=payload.user.full_name,
        is_active=1,
        is_superuser=0,
    )
    db.add(user)
    db.flush()

    membership = FirmMembershipORM(user_id=user.id, firm_id=firm.id, role="owner")
    db.add(membership)
    db.commit()

    token = create_access_token({"sub": user.id, "firm_id": firm.id})
    return Token(access_token=token, token_type="bearer")


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> Token:
    email = payload.email.lower()
    user = db.query(UserORM).filter(UserORM.email == email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password.")

    memberships = db.query(FirmMembershipORM).filter(FirmMembershipORM.user_id == user.id).all()
    if not memberships:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not part of any firm.")

    firm_id: Optional[str] = None
    if len(memberships) == 1:
        firm_id = memberships[0].firm_id
    else:
        if payload.firm_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Multiple firm memberships; specify firm_id.",
            )
        match = next((m for m in memberships if m.firm_id == payload.firm_id), None)
        if not match:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not part of requested firm.")
        firm_id = match.firm_id

    token = create_access_token({"sub": user.id, "firm_id": firm_id})
    return Token(access_token=token, token_type="bearer")


@router.get("/me", response_model=MeAuthResponse)
def me(ctx: RequestContext = Depends(get_current_context)) -> MeAuthResponse:
    roles: list[str] = []
    if ctx.membership and ctx.membership.role:
        roles = [ctx.membership.role]
    return MeAuthResponse(user=_build_user_read(ctx.user), firm=_build_firm_read(ctx.firm), roles=roles)
