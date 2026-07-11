from datetime import datetime, timezone
from contextlib import contextmanager
from sqlalchemy import create_engine, Column, String, Integer, Float, Boolean, DateTime, Text, CheckConstraint
from sqlalchemy.orm import declarative_base, sessionmaker
from config import settings

# Create engine
engine = create_engine(
    settings.DATABASE_URL, 
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class CreatorProfile(Base):
    __tablename__ = "creator_profiles"
    
    author_urn = Column(String, primary_key=True, index=True)
    display_name = Column(String, nullable=True)
    trust_score = Column(Float, default=0.5)
    times_seen = Column(Integer, default=0)
    times_hidden = Column(Integer, default=0)
    times_restored = Column(Integer, default=0)
    times_bookmarked = Column(Integer, default=0)
    last_seen_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("trust_score >= 0.0 AND trust_score <= 1.0", name="check_trust_score_bounds"),
    )

class TopicProfile(Base):
    __tablename__ = "topic_profiles"

    topic_name = Column(String, primary_key=True, index=True)
    interest_score = Column(Float, default=0.0) # -1.0 to 1.0
    times_interacted = Column(Integer, default=0)
    times_ignored = Column(Integer, default=0)

    __table_args__ = (
        CheckConstraint("interest_score >= -1.0 AND interest_score <= 1.0", name="check_interest_score_bounds"),
    )

class StyleProfile(Base):
    __tablename__ = "style_profiles"

    style_name = Column(String, primary_key=True, index=True)
    preference_score = Column(Float, default=0.0) # -1.0 to 1.0

    __table_args__ = (
        CheckConstraint("preference_score >= -1.0 AND preference_score <= 1.0", name="check_style_score_bounds"),
    )

class DecisionLog(Base):
    __tablename__ = "decision_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    post_urn = Column(String, nullable=True, index=True)
    author_urn = Column(String, index=True)
    author_name = Column(String, nullable=True)
    post_text = Column(Text, nullable=True)
    action_taken = Column(String, nullable=False) # hide, collapse, highlight, keep
    matched_detector = Column(String, nullable=True) # e.g. ai_slop, humble_brag
    explanation = Column(Text, nullable=True)
    user_corrected = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class FilterSetting(Base):
    __tablename__ = "filter_settings"

    detector_id = Column(String, primary_key=True)
    enabled = Column(Boolean, default=True)

# Context manager for DB sessions to ensure automatic closing
@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(bind=engine)
    
    # Initialize default filter settings
    defaults = [
        "ai_slop",
        "fake_expert",
        "news_aggregator",
        "sales_pitch",
        "humble_brag",
        "generic_motivation",
        "copy_paste_influencer"
    ]
    with get_db() as db:
        for detector in defaults:
            exists = db.query(FilterSetting).filter_by(detector_id=detector).first()
            if not exists:
                db.add(FilterSetting(detector_id=detector, enabled=True))
