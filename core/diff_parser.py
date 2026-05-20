from unidiff import PatchSet


def split_diff_by_file(diff_text):

    files = {}
    current_file = None
    current_content = []

    for line in diff_text.split("\n"):
        if line.startswith("diff --git"):
            if current_file:
                files[current_file] = "\n".join(current_content)

            current_file = line.split(" ")[2][2:]
            current_content = []
        else:
            current_content.append(line)

    if current_file:
        files[current_file] = "\n".join(current_content)

    return files


def clean_diff(diff_text):
    cleaned_lines = []

    for line in diff_text.split("\n"):
        if line.startswith("new file mode"):
            continue
        if line.startswith("deleted file mode"):
            continue
        if line.startswith("index "):
            continue

        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def extract_diff_with_positions(diff_text):

    cleaned_diff = clean_diff(diff_text)
    patch = PatchSet(cleaned_diff)

    diff_data = []

    for file in patch:

        for hunk in file:

            position = 0  # 🔥 position inside this hunk

            for line in hunk:
                position += 1  # 🔥 increment for EVERY line (important)

                if line.is_added:

                    # ❌ skip invalid lines
                    if line.target_line_no is None:
                        continue

                    normalized_line = line.value.replace("+", "").strip()
                    normalized_line = " ".join(normalized_line.split())

                    diff_data.append({
                        "file": file.path,
                        "line_content": normalized_line,
                        "line_number": int(line.target_line_no),  # file line
                        "position": position                      # 🔥 diff position
                    })

    return diff_data