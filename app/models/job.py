from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    company: Mapped[str | None] = mapped_column(String)
    location: Mapped[str | None] = mapped_column(String)
    job_type: Mapped[str | None] = mapped_column(String)
    eligibility: Mapped[str | None] = mapped_column(String)
    education: Mapped[str | None] = mapped_column(String)
    experience: Mapped[str | None] = mapped_column(String)
    short_desc: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    skills: Mapped[str | None] = mapped_column(Text)
    salary: Mapped[str | None] = mapped_column(String)
    last_date: Mapped[str | None] = mapped_column(String)
    apply_url: Mapped[str | None] = mapped_column(String)
    image_filename: Mapped[str | None] = mapped_column(String)
    posted_date: Mapped[date | None] = mapped_column(Date, server_default=func.current_date())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    # Phase 2 additions vs your Flask schema:
    source: Mapped[str | None] = mapped_column(String)  # 'internshala' | 'aggregator' | 'company_feed' | 'manual'
    dedup_hash: Mapped[str | None] = mapped_column(String, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
