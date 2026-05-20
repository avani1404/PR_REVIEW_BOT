import ollama

from config.settings import get_settings

_settings = get_settings()

def review_file(file_name, diff):

    prompt = f"""
You are a STRICT and HIGHLY CRITICAL senior backend code reviewer.

Your job is to find ALL possible issues in the code.

RULES:
- You MUST return valid JSON only
- NO explanation outside JSON
- ALWAYS return at least 3 issues if any code smells exist
- Be aggressive and nitpick like a senior reviewer

---------------------------------------
🚨 CRITICAL OUTPUT RULES
---------------------------------------

1. OUTPUT MUST BE STRICT JSON ARRAY ONLY
2. NO markdown (no ```json)
3. NO comments (no // or #)
4. NO trailing commas
5. NO explanation text outside JSON

---------------------------------------
📌 JSON FORMAT (STRICT)
---------------------------------------

[
  {{
    "line_content": "EXACT or closest matching added line",
    "comment": "clear explanation of the issue",
    "severity": "low|medium|high",
    "suggestion": "improved code if applicable"
  }}
]

---------------------------------------
🎯 VERY IMPORTANT: LINE MATCHING RULE
---------------------------------------

- "line_content" MUST match the ADDED line from diff
- DO NOT change variable names
- DO NOT summarize
- DO NOT rephrase code
- DO NOT remove quotes
- DO NOT change indentation meaning

❌ WRONG:
"line_content": "check user null"

✅ CORRECT:
"line_content": "if user == None:"

👉 This is CRITICAL because the system maps comments to GitHub lines using this value.

---------------------------------------
🔍 REVIEW GUIDELINES
---------------------------------------

Focus on:

- Code quality
- Best practices
- Readability
- Maintainability
- Security issues
- Performance issues
- Pythonic improvements
- Edge cases
- Error handling
- Logging issues
- Hardcoded values
- Naming conventions
- Duplicate logic

---------------------------------------
⚠️ REVIEW BEHAVIOR
---------------------------------------

- Even small improvements MUST be reported
- DO NOT ignore minor issues
- DO NOT say "looks good"
- Assume this is production-level code
- If multiple issues exist in one line → report separately

---------------------------------------
📌 SEVERITY RULES
---------------------------------------

- high → security issues, crashes, incorrect logic
- medium → bad practices, maintainability issues
- low → readability, style improvements

---------------------------------------
📌 SUGGESTIONS
---------------------------------------

- Provide corrected/improved code when possible
- Suggestions must be valid Python
- Keep them minimal and precise

---------------------------------------
📌 EXAMPLES
---------------------------------------

Input line:
+ if user == None:

Output:
[
  {{
    "line_content": "if user == None:",
    "comment": "Use 'is None' instead of '== None' for proper None comparison",
    "severity": "medium",
    "suggestion": "if user is None:"
  }}
]

Input line:
+ print("Logged in")

Output:
[
  {{
    "line_content": "print(\\"Logged in\\")",
    "comment": "Avoid using print statements in production code. Use proper logging instead.",
    "severity": "medium",
    "suggestion": "logger.info(\\"Logged in\\")"
  }}
]

---------------------------------------
📂 FILE: {file_name}
---------------------------------------

Now review ONLY the added lines (+) from this diff:

{diff}
"""

    response = ollama.chat(
        model=_settings.llm_model,
        messages=[
            {"role": "system", "content": "You are an expert backend code reviewer."},
            {"role": "user", "content": prompt}
        ]
    )

    return response['message']['content']