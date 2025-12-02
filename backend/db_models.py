from __future__ import annotations

import os
import uuid
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.types import JSON

from backend.db import Base


def _uuid_str() -> str:
    return str(uuid.uuid4())


class ClientORM(Base):
    __tablename__ = "clients"

    id = Column(String, primary_key=True, default=_uuid_str)
    name = Column(String, nullable=False)
    code = Column(String, nullable=True)
    status = Column(String, nullable=False, default="active")

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class EngagementORM(Base):
    __tablename__ = "engagements"

    id = Column(String, primary_key=True, default=_uuid_str)
    client_id = Column(String, ForeignKey("clients.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    period_start = Column(DateTime, nullable=True)
    period_end = Column(DateTime, nullable=True)
    status = Column(String, nullable=False, default="open")

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


JSONType = JSON


class FindingORM(Base):
    __tablename__ = "findings"

    id = Column(String, primary_key=True)
    engagement_id = Column(String, ForeignKey("engagements.id"), nullable=False, index=True)
    domain = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    code = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    metadata_json = Column(JSONType, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class DocumentORM(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    engagement_id = Column(String, ForeignKey("engagements.id"), index=True)
    filename = Column(String, nullable=False)
    content = Column(LargeBinary, nullable=False)
    type = Column(String, nullable=False)
    amount = Column(Float, nullable=True)
    date = Column(Date, nullable=True)
    counterparty = Column(String, nullable=True)
    external_ref = Column(String, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    uploaded_by = Column(String, default="demo", nullable=False)


class DocumentLinkORM(Base):
    __tablename__ = "document_links"

    id = Column(Integer, primary_key=True)
    engagement_id = Column(String, ForeignKey("engagements.id"), index=True)
    domain = Column(String, nullable=False)
    entry_id = Column(String, nullable=False)
    doc_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
