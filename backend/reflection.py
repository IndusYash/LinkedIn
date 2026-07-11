import logging
from database import get_db, DecisionLog, CreatorProfile

logger = logging.getLogger("reflection")

def process_user_correction(post_urn: str, action: str):
    """
    Asynchronous reflection engine to update SQLite memory DB profiles
    based on user interaction (e.g., restoring a post).
    """
    logger.info(f"Triggering Reflection Graph for post {post_urn} with correction action: {action}")
    
    try:
        with get_db() as db:
            # 1. Retrieve the decision log
            log = db.query(DecisionLog).filter_by(post_urn=post_urn).first()
            if not log:
                logger.warning(f"No decision log found for post {post_urn}. Cannot execute reflection.")
                return

            # Mark corrected
            log.user_corrected = True
            db.add(log)

            # 2. Retrieve creator profile
            creator = db.query(CreatorProfile).filter_by(author_urn=log.author_urn).first()
            if not creator:
                creator = CreatorProfile(
                    author_urn=log.author_urn,
                    display_name=log.author_name,
                    trust_score=0.5
                )

            # 3. Apply updates based on correction type
            if action == "restore":
                creator.times_restored += 1
                # Restore penalty: give back trust score and add bonus
                # Since hide/collapse penalizes -0.05, we restore +0.15 (gradual positive boost)
                creator.trust_score = min(1.0, creator.trust_score + 0.15)
                logger.info(f"Restored trust for {creator.display_name}. New score: {creator.trust_score}")
                
            elif action == "always_keep_creator":
                creator.trust_score = 1.0
                logger.info(f"Creator {creator.display_name} set to white-listed (trust=1.0)")
                
            elif action == "always_hide_creator":
                creator.trust_score = 0.0
                logger.info(f"Creator {creator.display_name} set to black-listed (trust=0.0)")

            db.add(creator)

    except Exception as e:
        logger.error(f"Error executing reflection engine: {e}")
