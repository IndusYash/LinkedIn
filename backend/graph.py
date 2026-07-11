import logging
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from config import settings
from database import get_db, CreatorProfile, TopicProfile, FilterSetting, DecisionLog
from schemas import PostContent, LLMReasoningResult, DetectorEnum

# Setup logger
logger = logging.getLogger("curator_graph")
logging.basicConfig(level=logging.INFO)

class CuratorState(TypedDict):
    post: PostContent
    creator_trust: float
    is_decisive: bool
    reasoning: Optional[LLMReasoningResult]
    final_action: str  # hide, collapse, highlight, keep
    matched_detector: Optional[str]
    explanation: Optional[str]

# Retrieve memory from SQLite
def retrieve_memory_node(state: CuratorState) -> CuratorState:
    post = state["post"]
    creator_trust = 0.5  # default neutral trust
    
    try:
        with get_db() as db:
            profile = db.query(CreatorProfile).filter_by(author_urn=post.author_urn).first()
            if profile:
                creator_trust = profile.trust_score
                # Update seen count
                profile.times_seen += 1
                profile.last_seen_at = profile.last_seen_at # resets default timestamp trigger
                db.add(profile)
            else:
                # Initialize profile
                new_profile = CreatorProfile(
                    author_urn=post.author_urn,
                    display_name=post.author_name,
                    trust_score=0.5,
                    times_seen=1
                )
                db.add(new_profile)
    except Exception as e:
        logger.error(f"Error reading DB in retrieve_memory_node: {e}")
        
    return {
        **state,
        "creator_trust": creator_trust,
        "is_decisive": False
    }

# Check simple heuristics before calling LLM
def heuristic_check_node(state: CuratorState) -> CuratorState:
    creator_trust = state["creator_trust"]
    post_text = state["post"].post_text.lower()
    
    # 1. Hard blacklist / whitelist creator heuristic
    if creator_trust <= 0.1:
        # User explicitly hates this creator
        return {
            **state,
            "is_decisive": True,
            "final_action": "hide",
            "matched_detector": "fake_expert",
            "explanation": "Creator is manually blacklisted / has zero trust score."
        }
    
    if creator_trust >= 0.9:
        # Highly trusted creator
        return {
            **state,
            "is_decisive": True,
            "final_action": "keep",
            "matched_detector": "none",
            "explanation": "Creator is highly trusted based on history."
        }

    # 2. Simple regex keyword heuristics (very cheap backup)
    # Marketing and sales pitch indicators
    pitch_keywords = [
        "buy now", "course launches", "limited seats", "use coupon", "pre-register",
        "dm me", "book a call", "calendly.com", "limited slots", "cohort starts",
        "register here", "dm '", "comment '", "marketing strategy", "marketing campaign",
        "grow your brand", "increase revenue", "scale your business", "b2b marketing",
        "lead generation", "personal branding", "brand growth"
    ]
    if any(kw in post_text for kw in pitch_keywords) and creator_trust < 0.6:
        return {
            **state,
            "is_decisive": True,
            "final_action": "collapse",
            "matched_detector": "sales_pitch",
            "explanation": "Triggered direct keyword heuristic for sales pitch / marketing."
        }

    # Wannabe teacher / cheat sheet spam indicators
    teacher_keywords = [
        "dsa sheet", "dsa problem", "cheat sheet", "cheat-sheet", 
        "commands every developer", "commands you should know", 
        "sql commands", "docker commands", "git commands", 
        "dsa cheat", "roadmap for developers", "git cheat", "docker cheat"
    ]
    if any(kw in post_text for kw in teacher_keywords) and creator_trust < 0.6:
        return {
            **state,
            "is_decisive": True,
            "final_action": "collapse",
            "matched_detector": "fake_expert",
            "explanation": "Triggered direct keyword heuristic for basic cheat sheet / teacher spam."
        }

    # Generic motivation indicators
    motivation_keywords = [
        "consistency is key", "grind never stops", "hustle mode", 
        "obsessed with getting better", "reps matter", "consistency compounds"
    ]
    if any(kw in post_text for kw in motivation_keywords) and creator_trust < 0.6:
        return {
            **state,
            "is_decisive": True,
            "final_action": "collapse",
            "matched_detector": "generic_motivation",
            "explanation": "Triggered direct keyword heuristic for motivation spam."
        }

    return state

# Call Groq API for reasoning if heuristics are indecisive
def groq_reasoner_node(state: CuratorState) -> CuratorState:
    if state.get("is_decisive"):
        return state

    post = state["post"]
    
    if not settings.GROQ_API_KEY:
        logger.warning("GROQ_API_KEY is not set. Bypassing LLM Node.")
        return {
            **state,
            "is_decisive": True,
            "final_action": "keep",
            "matched_detector": "none",
            "explanation": "Groq API key not configured. Allowed default visibility."
        }

    try:
        # Initialize Groq LLM with structured outputs
        llm = ChatGroq(
            groq_api_key=settings.GROQ_API_KEY,
            model_name="llama-3.3-70b-versatile",
            temperature=0.0
        )
        structured_llm = llm.with_structured_output(LLMReasoningResult)

        # Curation prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "You are the reasoning node of the 'LinkedIn Feed Curator' browser extension. "
                "Your objective is to act as an attention guardian, protecting the user's attention from low-value noise.\n\n"
                "Review the post details and categorize it into one of these specific detectors if applicable:\n"
                "- 'ai_slop': AI-generated text ('I asked GPT to...', generic AI advice, obvious ChatGPT formatting/style), generic infographics, engagement/save bait ('Save this post for revision').\n"
                "- 'fake_expert': Low technical depth, buzzword-heavy posts, over-simplifying engineering problems, superficial hot takes. Includes 'wannabe teachers' posting extremely basic cheat sheets, trivial lists of commands (e.g., standard Docker/Git commands, basic syntax lists), or surface-level tutorials aimed at beginners for engagement farming, without offering any unique professional insights, production benchmarks, or deep architectural breakdowns.\n"
                "- 'news_aggregator': Reposting news screenshots, model releases (e.g., Anthropic updates, OpenAI launches), or press announcements with superficial bullet-points, without adding deep custom evaluation or integration code.\n"
                "- 'sales_pitch': Job recruitment, selling online courses, services marketing, SaaS pitching, promotional links. Includes portfolio showcases, self-promotional case studies, or 'how-I-did-it' craft breakdowns that conclude with a client solicitation, service pitch, call-to-action (CTA), or lead generation hook (e.g., 'DM me to start', 'you know where to find me', 'let's build this for your brand').\n"
                "- 'humble_brag': Self-aggrandizing self-congratulations, celebrating trivial accomplishments repetitively, or posting awards with false modesty (e.g., 'I am not sharing this to brag, but...'). NOTE: Major, prestigious life events (e.g., getting a job at highly competitive institutes like ISRO, NASA, CERN, winning national scientific/tech awards, publishing academic papers, or graduating) are NOT humble brags and must be classified as 'none'.\n"
                "- 'generic_motivation': Hustle culture platitudes ('The reps matter', 'Keep raising the bar', 'Consistency beats talent'), corporate fortune cookies, generic career advice.\n"
                "- 'copy_paste_influencer': Typical LinkedIn influencer format style: short single-sentence lines separated by double linebreaks, rags-to-riches hustle stories (e.g., 'From ₹15,000 to Times Square', 'I got fired, now I am CEO'), engagement hooks, or highly repetitive templates.\n"
                "- 'none': If the post contains genuine technical insights, original research, system architecture breakdowns, code benchmarks, or highly authentic/uniquely educational stories.\n\n"
                "Output your scores and matched detector accurately."
            )),
            ("user", "Author: {author_name}\n\nPost Content:\n{post_text}")
        ])

        # Run model
        chain = prompt | structured_llm
        result: LLMReasoningResult = chain.invoke({
            "author_name": post.author_name or "Unknown",
            "post_text": post.post_text
        })

        return {
            **state,
            "reasoning": result
        }

    except Exception as e:
        logger.error(f"Error in Groq reasoner node: {e}")
        # Fail-open: Let the post be visible if the LLM fails
        return {
            **state,
            "is_decisive": True,
            "final_action": "keep",
            "matched_detector": "none",
            "explanation": f"Failed to execute LLM node: {str(e)}"
        }

# Determine action based on rules, configs, and reasoning scores
def decision_policy_node(state: CuratorState) -> CuratorState:
    if state.get("is_decisive"):
        # Save decision to log before ending
        save_decision_log(state)
        return state

    reasoning: LLMReasoningResult = state.get("reasoning")
    if not reasoning:
        state["final_action"] = "keep"
        state["matched_detector"] = "none"
        state["explanation"] = "No reasoning structure available."
        save_decision_log(state)
        return state

    detector = reasoning.matched_detector.value
    explanation = reasoning.explanation
    
    action = "keep"
    
    # Check if this detector is enabled in settings
    detector_enabled = True
    if detector != "none":
        try:
            with get_db() as db:
                setting = db.query(FilterSetting).filter_by(detector_id=detector).first()
                if setting:
                    detector_enabled = setting.enabled
        except Exception as e:
            logger.error(f"DB Error reading filter setting: {e}")

    # Determine visual curation action
    if detector != "none" and detector_enabled:
        if reasoning.confidence_score >= 0.7:
            # Sales Pitch or direct slop -> Hide completely
            if detector in ["sales_pitch"]:
                action = "hide"
            else:
                action = "collapse"
        elif reasoning.confidence_score >= 0.4:
            action = "collapse"
    else:
        # Check high-value highlight criteria
        if (reasoning.technical_depth_score >= 0.7 and 
            reasoning.originality_score >= 0.7 and 
            reasoning.promotional_score < 0.3):
            action = "highlight"

    new_state = {
        **state,
        "final_action": action,
        "matched_detector": detector if detector != "none" else None,
        "explanation": explanation
    }

    # Save to database log
    save_decision_log(new_state)

    # Adjust creator seen profiles
    update_creator_profile_stats(new_state)

    return new_state

def save_decision_log(state: CuratorState):
    try:
        with get_db() as db:
            log = DecisionLog(
                post_urn=state["post"].post_urn,
                author_urn=state["post"].author_urn,
                author_name=state["post"].author_name,
                post_text=state["post"].post_text,
                action_taken=state["final_action"],
                matched_detector=state["matched_detector"],
                explanation=state["explanation"]
            )
            db.add(log)
    except Exception as e:
        logger.error(f"Error saving decision log to DB: {e}")

def update_creator_profile_stats(state: CuratorState):
    # Minor adjustment based on immediate action
    if state["final_action"] == "keep":
        return
    try:
        with get_db() as db:
            profile = db.query(CreatorProfile).filter_by(author_urn=state["post"].author_urn).first()
            if profile:
                if state["final_action"] in ["hide", "collapse"]:
                    profile.times_hidden += 1
                    # Gradual trust score penalty
                    profile.trust_score = max(0.0, profile.trust_score - 0.05)
                db.add(profile)
    except Exception as e:
        logger.error(f"Error updating creator profile stats: {e}")

# Build LangGraph StateGraph
def build_curator_graph():
    builder = StateGraph(CuratorState)

    builder.add_node("retrieve_memory", retrieve_memory_node)
    builder.add_node("heuristic_check", heuristic_check_node)
    builder.add_node("groq_reasoner", groq_reasoner_node)
    builder.add_node("decision_policy", decision_policy_node)

    builder.set_entry_point("retrieve_memory")
    
    builder.add_edge("retrieve_memory", "heuristic_check")
    builder.add_edge("heuristic_check", "groq_reasoner")
    builder.add_edge("groq_reasoner", "decision_policy")
    builder.add_edge("decision_policy", END)

    return builder.compile()

# Thread-safe graph runner instance
curator_flow = build_curator_graph()

def run_curator(post: PostContent) -> dict:
    initial_state = CuratorState(
        post=post,
        creator_trust=0.5,
        is_decisive=False,
        reasoning=None,
        final_action="keep",
        matched_detector=None,
        explanation=None
    )
    try:
        result = curator_flow.invoke(initial_state)
        return {
            "post_urn": result["post"].post_urn,
            "action": result["final_action"],
            "matched_detector": result["matched_detector"],
            "explanation": result["explanation"]
        }
    except Exception as e:
        logger.error(f"Error in run_curator Graph: {e}")
        return {
            "post_urn": post.post_urn,
            "action": "keep",
            "matched_detector": None,
            "explanation": f"Graph execution error: {str(e)}"
        }
