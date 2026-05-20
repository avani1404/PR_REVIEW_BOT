# 🔥 Import the embedding + similarity functions from their actual location.
# Without these imports, get_embedding() and cosine_similarity() below would
# raise NameError at runtime and crash the deduplication step entirely.
from core.embedding_utils import get_embedding, cosine_similarity
import logging

from config.settings import get_settings

_settings = get_settings()


logger = logging.getLogger(__name__)


def deduplicate_comments(ai_reviews, threshold=None):
    if threshold is None:
        threshold = _settings.dedup_threshold

    unique_reviews = []
    seen_embeddings = []
    seen_keywords = []

    def extract_keywords(text):
        text = text.lower()
        keywords = []

        if "print" in text or "logging" in text or "logger" in text:
            keywords.append("logging")

        if "variable" in text or "name" in text:
            keywords.append("naming")

        if "none" in text:
            keywords.append("none_check")

        if "performance" in text or "optimize" in text:
            keywords.append("performance")

        return keywords

    for review in ai_reviews:

        comment = review.get("comment", "")

        if not comment:
            continue

        current_keywords = extract_keywords(comment)

        # 🔥 KEYWORD CHECK
        keyword_duplicate = False
        for seen_kw in seen_keywords:
            if set(current_keywords) & set(seen_kw):
                logger.info("Keyword duplicate skipped: %s", comment)
                keyword_duplicate = True
                break

        if keyword_duplicate:
            continue

        # 🔥 EMBEDDING CHECK
        try:
            emb = get_embedding(comment)
        except Exception:
            logger.exception("Embedding failed during deduplication for comment: %s", comment)
            continue

        is_duplicate = False

        for seen_emb in seen_embeddings:
            sim = cosine_similarity(emb, seen_emb)

            if sim > threshold:
                logger.info("Semantic duplicate skipped (threshold=%s): %s", threshold, comment)
                is_duplicate = True
                break

        if is_duplicate:
            continue

        # ✅ STORE
        seen_embeddings.append(emb)
        seen_keywords.append(current_keywords)

        logger.debug("Keeping unique comment: %s", comment)

        unique_reviews.append(review)

    return unique_reviews