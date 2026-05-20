# 🔥 rapidfuzz: a fast fuzzy string matching library.
# is_similar() uses fuzz.ratio() which returns a percentage (0-100)
# representing how similar two strings are. Without this import,
# the function would crash with NameError on its very first call.
from rapidfuzz import fuzz


def parse_pr_url(pr_url):
    """
    Parse a GitHub PR URL into (owner, repo, pr_number).

    Example:
        Input:  https://github.com/maheavaa/myrepo/pull/42
        Output: ("maheavaa", "myrepo", "42")
    """
    parts = pr_url.strip().split("/")
    return parts[3], parts[4], parts[6]


# =========================
# 📌 FUZZY LOGIC
# =========================
def is_similar(a, b, threshold=85):
    """
    Returns True if strings 'a' and 'b' are at least `threshold`% similar.
    Useful when LLM output has tiny formatting differences from actual code.
    """
    return fuzz.ratio(a, b) >= threshold