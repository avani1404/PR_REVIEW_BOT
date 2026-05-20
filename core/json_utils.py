import re
import json
import logging


logger = logging.getLogger(__name__)

def extract_json_from_text(text):
    """
    Ultra-robust JSON extractor for messy LLM outputs
    """

    # -------------------------
    # 🔧 Step 1: Remove comments
    # -------------------------
    text = re.sub(r'//.*', '', text)
    text = re.sub(r'#.*', '', text)

    # -------------------------
    # 🔧 Step 2: Fix quotes inside strings
    # -------------------------
    text = re.sub(r'print\("([^"]*)"\)', r'print(\\"\1\\")', text)

    # -------------------------
    # 🔧 Step 3: Extract JSON array
    # -------------------------
    start = text.find("[")
    end = text.rfind("]")

    if start == -1 or end == -1:
        return []

    json_str = text[start:end+1]

    # -------------------------
    # 🔧 Step 4: Try normal parse
    # -------------------------
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.debug("Primary JSON parse failed; using fallback extraction: %s", exc)

    # -------------------------
    # 🔥 Step 5: FALLBACK
    # -------------------------
    objects = re.findall(r'\{[^\}]*\}', json_str)

    results = []

    for obj in objects:
        try:
            obj = re.sub(r',\s*}', '}', obj)
            obj = obj.replace('("', '(\\"').replace('")', '\\")')
            parsed = json.loads(obj)
            results.append(parsed)
        except (json.JSONDecodeError, TypeError):
            continue

    return results