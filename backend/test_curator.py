import sys
import os

# Adjust path to import backend modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from schemas import PostContent
from graph import run_curator
from database import init_db, get_db, DecisionLog, CreatorProfile

def run_tests():
    print("--------------------------------------------------")
    print("LinkedIn Attention Guardian: Initializing Test Suite...")
    print("--------------------------------------------------")
    
    # 1. Initialize DB
    init_db()
    
    # Pre-configure a blacklisted creator in SQLite for Heuristic Test
    with get_db() as db:
        blacklisted = db.query(CreatorProfile).filter_by(author_urn="/in/spammer-profile").first()
        if not blacklisted:
            db.add(CreatorProfile(
                author_urn="/in/spammer-profile",
                display_name="Clickbait Spammer",
                trust_score=0.0  # Zero trust = Blacklist
            ))
            print("Configured mock blacklisted creator in database.")

    # Test cases
    test_posts = [
        # Case A: Blacklisted Creator (Heuristic Test)
        PostContent(
            post_urn="urn:li:activity:9999999991",
            author_urn="/in/spammer-profile",
            author_name="Clickbait Spammer",
            post_text="You won't believe this one trick to make 10k a month!"
        ),
        # Case B: Sales Pitch keyword (Heuristic Test)
        PostContent(
            post_urn="urn:li:activity:9999999992",
            author_urn="/in/recruiter-profile",
            author_name="Job recruiter",
            post_text="We have multiple open positions! Buy now, limited seats, use coupon code JOIN50."
        ),
        # Case C: Technical Post (Should be Kept or Highlighted)
        PostContent(
            post_urn="urn:li:activity:9999999993",
            author_urn="/in/rust-engineer",
            author_name="Alice (Rust Dev)",
            post_text="To design a high-throughput distributed lock manager, we implemented an LSM tree in Rust. Here are benchmark figures comparing key-value lookups against RocksDB showing a 40% reduction in p99 latency."
        )
    ]

    print("\nExecuting Local Curation Flow (Fast Path & Heuristics)...")
    for i, post in enumerate(test_posts, 1):
        print(f"\n[Test #{i}] Curating post from: {post.author_name}")
        print(f"Content: '{post.post_text[:80]}...'")
        
        result = run_curator(post)
        
        print(f"RESULT -> Action: {result['action'].upper()}")
        print(f"RESULT -> Matched Detector: {result['matched_detector']}")
        print(f"RESULT -> Explanation: {result['explanation']}")

    # Clean up test database modifications
    print("\nCleaning up test logs from database...")
    try:
        with get_db() as db:
            db.query(DecisionLog).filter(DecisionLog.post_urn.like("urn:li:activity:999999999%")).delete(synchronize_session=False)
            db.query(CreatorProfile).filter_by(author_urn="/in/spammer-profile").delete()
        print("Cleanup completed.")
    except Exception as e:
        print(f"Cleanup error: {e}")

    print("\n--------------------------------------------------")
    print("Tests completed successfully!")
    print("--------------------------------------------------")

if __name__ == "__main__":
    run_tests()
