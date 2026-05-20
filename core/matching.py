from core.embedding_utils import get_embedding, cosine_similarity
from core.formatting import format_severity
import logging

from config.settings import get_settings

_settings = get_settings()


logger = logging.getLogger(__name__)

def map_comments_to_positions(ai_reviews, diff_data):

    mapped_comments = []

    # Pre-compute diff embeddings once to avoid O(reviews * lines) repeat calls.
    diff_candidates = []
    for diff_line in diff_data:
        diff_text = diff_line.get("line_content", "")
        if not diff_text:
            continue

        try:
            diff_embedding = get_embedding(diff_text)
        except Exception:
            logger.exception("Embedding failed for diff line during precompute: %s", diff_text)
            continue

        diff_candidates.append((diff_line, diff_embedding))

    for review in ai_reviews:

        # -------------------------
        # 🔹 Extract fields safely
        # -------------------------
        ai_line = review.get("line_content", "")
        ai_line = ai_line.replace("+", "").strip()
        ai_line = " ".join(ai_line.split())

        comment = review.get("comment", "")
        severity = review.get("severity", "low")
        suggestion = review.get("suggestion", "")

        # ❌ Skip invalid entries
        if not ai_line or not comment:
            continue

        # -------------------------
        # 🔍 Generate embedding for AI line
        # -------------------------
        try:
            ai_embedding = get_embedding(ai_line)
        except Exception:
            logger.exception("Embedding failed for AI review line: %s", ai_line)
            continue

        # -------------------------
        # 🔍 Find best matching diff line
        # -------------------------
        best_match = None
        best_score = -1

        for diff_line, diff_embedding in diff_candidates:
            score = cosine_similarity(ai_embedding, diff_embedding)

            if score > best_score:
                best_score = score
                best_match = diff_line

        # -------------------------
        # ❌ Skip low confidence matches
        # -------------------------
        if not best_match or best_score < _settings.match_threshold:
            logger.info("Skipping low-confidence semantic match (score=%.2f): %s", best_score, ai_line)
            continue

        if not best_match.get("line_number"):
            continue

        # -------------------------
        # 🎨 Format comment body
        # -------------------------
        body = format_severity(comment, severity)

        if suggestion:
            suggestion_clean = suggestion.replace("+", "").strip()
            body += f"\n\n```suggestion\n{suggestion_clean}\n```"

        logger.info(
            "Final semantic match: '%s' -> '%s' (score=%.2f)",
            ai_line,
            best_match["line_content"],
            best_score,
        )

        # -------------------------
        # 📌 Add mapped comment
        # -------------------------
        mapped_comments.append({
            "path": best_match["file"],
            "line": int(best_match["line_number"]),
            "body": body
        })

    return mapped_comments