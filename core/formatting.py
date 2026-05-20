def format_severity(comment, severity):
    severity = severity.lower()

    if severity == "high":
        return f"🔴 **HIGH**: {comment}"
    elif severity == "medium":
        return f"🟡 **MEDIUM**: {comment}"
    else:
        return f"🟢 **LOW**: {comment}"