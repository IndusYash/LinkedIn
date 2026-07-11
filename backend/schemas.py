from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

class DetectorEnum(str, Enum):
    AI_SLOP = "ai_slop"
    FAKE_EXPERT = "fake_expert"
    NEWS_AGGREGATOR = "news_aggregator"
    SALES_PITCH = "sales_pitch"
    HUMBLE_BRAG = "humble_brag"
    GENERIC_MOTIVATION = "generic_motivation"
    COPY_PASTE_INFLUENCER = "copy_paste_influencer"
    NONE = "none"

# Extension inputs
class PostContent(BaseModel):
    post_urn: Optional[str] = None
    author_urn: str
    author_name: Optional[str] = None
    post_text: str

# API Curation responses
class CurateResponse(BaseModel):
    post_urn: Optional[str] = None
    action: str  # hide, collapse, highlight, keep
    matched_detector: Optional[str] = None
    explanation: Optional[str] = None

# Extension user actions
class CorrectionRequest(BaseModel):
    post_urn: str
    action: str  # restore, always_keep_creator, always_hide_creator

class FilterUpdate(BaseModel):
    detector_id: str
    enabled: bool

# Filter status items
class FilterSettingSchema(BaseModel):
    detector_id: str
    enabled: bool

# Dashboard stats response
class StatsResponse(BaseModel):
    total_processed: int
    kept_count: int
    hidden_count: int
    collapsed_count: int
    highlighted_count: int
    detector_breakdown: dict

# Structured output from LLM (Groq)
class LLMReasoningResult(BaseModel):
    technical_depth_score: float = Field(
        ..., 
        description="Value from 0.0 (extremely shallow/platitude) to 1.0 (highly technical, benchmark driven, deep explanation)"
    )
    promotional_score: float = Field(
        ..., 
        description="Value from 0.0 (not promotional) to 1.0 (pure marketing, selling a course, hiring pitch, link bait)"
    )
    originality_score: float = Field(
        ..., 
        description="Value from 0.0 (boilerplate, rephrasing public news, standard format) to 1.0 (highly unique insights, personal experiments)"
    )
    matched_detector: DetectorEnum = Field(
        ..., 
        description="The primary detector triggered. Use 'none' if the post is organic, original, and does not match any noise category."
    )
    explanation: str = Field(
        ..., 
        description="A short 1-sentence explanation of why it fits this detector or is of high/low quality."
    )
    confidence_score: float = Field(
        ..., 
        description="Confidence in this evaluation, from 0.0 (completely uncertain) to 1.0 (highly confident)."
    )
