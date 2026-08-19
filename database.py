"""
database.py
-----------
SQLAlchemy models + connection setup for the NABA Tech Textile QC app.

Design notes:
- Multi-tenant: every table that holds factory-specific data carries a
  factory_id so one Postgres database can safely host many white-labeled
  factory clients.
- Location hierarchy: Factory -> Destination -> Unit -> Hall (matches the
  "Sohrab Goth / Landhi / New Karachi -> Unit -> Hall 1,2,3" structure
  described by the client).
- Department is a plain string field ("cutting" | "stitching" | "checking" |
  "packing") rather than 4 separate tables, because the 4 manual registers
  share ~80% of their columns (Customer, PO#, Design, Article, Color, Size,
  Total Pieces, Sample Size, Defects, Status). Department-specific columns
  that don't apply to every form are kept nullable on InspectionReport, and
  department-specific fields (GSM, Ply Height, Machine No, Checker#, etc.)
  live in the `extra` JSON column so we don't need a schema migration every
  time a factory tweaks a form.
"""

import os
import enum
import datetime as dt
from contextlib import contextmanager

from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, Date, DateTime,
    ForeignKey, Enum, Float, Text, JSON, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from dotenv import load_dotenv

load_dotenv()


def _get_database_url() -> str:
    """
    Local dev: reads DATABASE_URL from .env (via python-dotenv).
    Streamlit Community Cloud deployment: reads it from st.secrets
    (Settings -> Secrets in the Streamlit Cloud dashboard), since Cloud
    deployments don't upload your local .env file (it's git-ignored on
    purpose — it holds real database credentials).
    """
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    try:
        import streamlit as st
        return st.secrets["DATABASE_URL"]
    except Exception:
        return "postgresql://naba_user:changeme@localhost:5432/naba_qc"


DATABASE_URL = _get_database_url()

# pool_pre_ping avoids "server closed the connection" errors on free-tier /
# low-traffic Postgres hosts (Render/Railway) that idle-close connections.
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=280)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


# ---------------------------------------------------------------- Enums ----
class UserRole(str, enum.Enum):
    SUPER_MASTER_ADMIN = "super_master_admin"   # hidden, cross-factory
    MAIN_ADMIN = "main_admin"                   # full factory control
    ASSISTANT_ADMIN = "assistant_admin"          # delegated admin rights
    HALL_MANAGER = "hall_manager"                # single hall/unit incharge
    FLOOR_INSPECTOR = "floor_inspector"          # mobile data entry only


class Severity(str, enum.Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class Department(str, enum.Enum):
    CUTTING = "cutting"
    STITCHING = "stitching"          # inline stitching
    CHECKING = "checking"
    PACKING = "packing"


class LotStatus(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    PENDING = "pending"


# --------------------------------------------------------------- Models ----
class Factory(Base):
    """One white-labeled tenant / client factory."""
    __tablename__ = "factories"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    logo_path = Column(String(300), nullable=True)
    gm_quality_name = Column(String(150), nullable=True)
    qc_manager_name = Column(String(150), nullable=True)
    admin_name = Column(String(150), nullable=True)
    license_expiry = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    destinations = relationship("Destination", back_populates="factory", cascade="all, delete-orphan")
    users = relationship("User", back_populates="factory", cascade="all, delete-orphan")


class Destination(Base):
    """Top-level site, e.g. Sohrab Goth, Landhi, New Karachi."""
    __tablename__ = "destinations"

    id = Column(Integer, primary_key=True)
    factory_id = Column(Integer, ForeignKey("factories.id"), nullable=False)
    name = Column(String(150), nullable=False)

    factory = relationship("Factory", back_populates="destinations")
    units = relationship("Unit", back_populates="destination", cascade="all, delete-orphan")


class Unit(Base):
    __tablename__ = "units"

    id = Column(Integer, primary_key=True)
    destination_id = Column(Integer, ForeignKey("destinations.id"), nullable=False)
    name = Column(String(150), nullable=False)

    destination = relationship("Destination", back_populates="units")
    halls = relationship("Hall", back_populates="unit", cascade="all, delete-orphan")


class Hall(Base):
    __tablename__ = "halls"

    id = Column(Integer, primary_key=True)
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=False)
    name = Column(String(100), nullable=False)   # "Hall 1", "Hall 2"...

    unit = relationship("Unit", back_populates="halls")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("factory_id", "username", name="uq_factory_username"),)

    id = Column(Integer, primary_key=True)
    factory_id = Column(Integer, ForeignKey("factories.id"), nullable=True)  # null for Super Master Admin
    username = Column(String(80), nullable=False)
    password_hash = Column(String(200), nullable=False)
    full_name = Column(String(150), nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    hall_id = Column(Integer, ForeignKey("halls.id"), nullable=True)  # scoping for hall manager / inspector
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    must_reset_password = Column(Boolean, default=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    factory = relationship("Factory", back_populates="users")
    hall = relationship("Hall")


class DefectCode(Base):
    """
    Per-department defect key, matching the A/B/C... columns printed on the
    right-hand side of each register (e.g. Cutting: A=Fabric Hole,
    B=Knitting Line ...). Factories can add/edit their own on top of the
    seeded defaults, which is what "Dynamic Defects" means in the spec.
    """
    __tablename__ = "defect_codes"
    __table_args__ = (UniqueConstraint("factory_id", "department", "code", name="uq_factory_dept_code"),)

    id = Column(Integer, primary_key=True)
    factory_id = Column(Integer, ForeignKey("factories.id"), nullable=False)
    department = Column(Enum(Department), nullable=False)
    code = Column(String(5), nullable=False)          # "A", "AA", "AB"...
    label = Column(String(150), nullable=False)        # "Fabric Hole"
    default_severity = Column(Enum(Severity), nullable=False, default=Severity.MINOR)
    is_active = Column(Boolean, default=True)


class BrandMaster(Base):
    """Custom brands a factory has typed in, beyond the 4 built-in defaults
    (Ikea/Vervial/Brandrom/Token fly), so they reappear in the dropdown."""
    __tablename__ = "brand_master"
    __table_args__ = (UniqueConstraint("factory_id", "name", name="uq_factory_brand"),)

    id = Column(Integer, primary_key=True)
    factory_id = Column(Integer, ForeignKey("factories.id"), nullable=False)
    name = Column(String(80), nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)


class ArticleMaster(Base):
    """
    Remembers the last-known specs for an Article Number so the Data Entry
    form can auto-fill Item/Color/Size/Lot No/GSM the next time the same
    Article Number is typed. Lot No and GSM stay editable in the form even
    after auto-fill (manual override), since those can differ per batch.
    """
    __tablename__ = "article_master"
    __table_args__ = (UniqueConstraint("factory_id", "article_number", name="uq_factory_article"),)

    id = Column(Integer, primary_key=True)
    factory_id = Column(Integer, ForeignKey("factories.id"), nullable=False)
    article_number = Column(String(80), nullable=False)
    item = Column(String(80))
    color = Column(String(80))
    size = Column(String(40))
    lot_no = Column(String(80))
    gsm = Column(String(40))
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)


class InspectionReport(Base):
    """
    One header row = one filled register sheet (one date/section/table for
    a department). Line items (defect quantities) live in InspectionDefectEntry.
    """
    __tablename__ = "inspection_reports"

    id = Column(Integer, primary_key=True)
    factory_id = Column(Integer, ForeignKey("factories.id"), nullable=False)
    hall_id = Column(Integer, ForeignKey("halls.id"), nullable=False)
    department = Column(Enum(Department), nullable=False)

    report_date = Column(Date, nullable=False, default=dt.date.today)
    customer = Column(String(150))
    po_number = Column(String(80))          # "PO / MB" in the UI
    design = Column(String(80))             # "Item" in the UI
    article = Column(String(80))            # "Article Number" in the UI
    color = Column(String(80))
    size = Column(String(40))
    brand = Column(String(50), nullable=True)   # Ikea / Vervial / Brandrom / Token fly
    week = Column(String(20), nullable=True)    # Week number

    total_inspected = Column(Integer, default=0)
    sample_size = Column(Integer, default=0)
    total_defects = Column(Integer, default=0)
    defective_percentage = Column(Float, default=0.0)
    aql_level = Column(String(30), nullable=True)      # e.g. "MAJ 2.5, MIN 4.0"
    status = Column(Enum(LotStatus), default=LotStatus.PENDING)

    # Department-specific extra fields that don't apply to every register
    # (GSM, Ply Height, Fabric Width, Cut Size for Cutting; Machine No,
    # Operation No for Stitching; Checker# for Checking, etc.)
    extra = Column(JSON, default=dict)

    photo_path = Column(String(300), nullable=True)    # compressed defect photo
    remarks = Column(Text, nullable=True)

    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    prepared_by = Column(String(150), nullable=True)
    checked_by = Column(String(150), nullable=True)
    reviewed_by = Column(String(150), nullable=True)

    synced = Column(Boolean, default=True)              # false while queued offline on device
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

    hall = relationship("Hall")
    defect_entries = relationship("InspectionDefectEntry", back_populates="report", cascade="all, delete-orphan")


class InspectionDefectEntry(Base):
    """One defect-code quantity line under a report (Major/Minor breakdown)."""
    __tablename__ = "inspection_defect_entries"

    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("inspection_reports.id"), nullable=False)
    defect_code_id = Column(Integer, ForeignKey("defect_codes.id"), nullable=False)
    quantity = Column(Integer, default=0)
    severity = Column(Enum(Severity), nullable=False)

    report = relationship("InspectionReport", back_populates="defect_entries")
    defect_code = relationship("DefectCode")


class AuditLog(Base):
    """Immutable trail: who changed/deleted what, and the before/after value."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(20), nullable=False)   # "create" | "update" | "delete"
    table_name = Column(String(80), nullable=False)
    record_id = Column(Integer, nullable=False)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    timestamp = Column(DateTime, default=dt.datetime.utcnow)


# ---------------------------------------------------------------- Helpers --
def init_db():
    """Create all tables. Safe to call repeatedly (no-op if they exist)."""
    Base.metadata.create_all(engine)


@contextmanager
def get_session():
    """Usage: with get_session() as db: db.query(...)"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
