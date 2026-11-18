import re
import json
import unicodedata
import pandas as pd

from pathlib import Path
from collections import defaultdict


# ============================================================
# 1. CONFIGURATION
# ============================================================

BASE_DIR = Path(".")

MARKDOWN_DIR = BASE_DIR / "data" / "md"
CSV_PATH = BASE_DIR / "data" / "selected_dataset_list.csv"

OUTPUT_DIR = BASE_DIR / "dataset"

REMOVED_PAGES_PATH = BASE_DIR / "removed_pages.csv"
MISSING_MARKDOWN_PATH = BASE_DIR / "missing_markdown.csv"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# 2. OPINION PAGE KEYWORDS
# ============================================================

# A page is removed if it contains ANY of these phrases.
#
# IMPORTANT:
# These are deliberately specific phrases. Avoid generic
# keywords such as "kiểm toán" or "ý kiến" because they
# could appear in unrelated financial report sections.

OPINION_KEYWORDS = [
    "ý kiến của kiểm toán viên",
    "ý kiến kiểm toán",
    "ý kiến chấp nhận toàn phần",
    "ý kiến ngoại trừ",
    "ý kiến trái ngược",
    "từ chối đưa ra ý kiến",
    "cơ sở của ý kiến ngoại trừ",
    "cơ sở của ý kiến trái ngược",
    "cơ sở của việc từ chối đưa ra ý kiến",
    "cơ sở đưa ra ý kiến",
    "chúng tôi đã kiểm toán báo cáo tài chính",
]


# ============================================================
# 3. PAGE SEPARATOR
# ============================================================

# Supports both:
# <!-- Page 2 -->
# \<!-- Page 2 -->

PAGE_SEPARATOR_PATTERN = re.compile(
    r"(?m)^[ \t]*\\?<!--[ \t]*Page[ \t]+(\d+)[ \t]*-->[ \t]*$",
    re.IGNORECASE,
)


# ============================================================
# 4. TEXT CLEANING
# ============================================================

def clean_text(text):
    # Normalize Unicode
    text = unicodedata.normalize("NFC", text)

    # Normalize Windows and Mac line endings
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    # Remove null bytes and unwanted control characters.
    # Keep newline and tab.
    text = "".join(
        char for char in text
        if char in "\n\t" or unicodedata.category(char) != "Cc"
    )

    # Remove zero-width and BOM characters
    text = text.replace("\ufeff", "")
    text = text.replace("\u200b", "")
    text = text.replace("\u200c", "")
    text = text.replace("\u200d", "")

    text = text.replace("□", "")

    # Convert special characters
    text = text.replace(r"\|", "|")
    text = text.replace(r"–", "-")
    text = text.replace(r"，", ",")

    # Remove trailing spaces and tabs from every line
    lines = [
        line.rstrip(" \t")
        for line in text.split("\n")
    ]

    text = "\n".join(lines)

    # Remove spaces at the beginning/end of the document
    text = text.strip()

    # Limit excessive consecutive blank lines to two
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text


# ============================================================
# 5. FIND OPINION KEYWORDS
# ============================================================

def find_opinion_keywords(page_text):
    normalized_text = unicodedata.normalize(
        "NFC", page_text
    ).lower()

    matches = []

    for keyword in OPINION_KEYWORDS:
        if keyword.lower() in normalized_text:
            matches.append(keyword)

    return matches


# ============================================================
# 6. SPLIT MARKDOWN INTO PAGES
# ============================================================

def split_into_pages(text):
    matches = list(PAGE_SEPARATOR_PATTERN.finditer(text))

    if not matches:
        return [
            {
                "page": 1,
                "text": text
            }
        ]

    pages = []

    # Content before the first separator
    first_content = text[:matches[0].start()].strip()

    if first_content:
        pages.append({
            "page": 1,
            "text": first_content
        })

    for i, match in enumerate(matches):

        page_number = int(match.group(1))

        start = match.end()

        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            end = len(text)

        page_content = text[start:end].strip()

        pages.append({
            "page": page_number,
            "text": page_content
        })

    return pages


# ============================================================
# 7. PROCESS ONE REPORT
# ============================================================

def process_report(report_id, markdown_path):

    original_text = markdown_path.read_text(
        encoding="utf-8"
    )

    # Split into individual pages
    pages = split_into_pages(original_text)

    kept_pages = []
    removed_pages = []

    for page in pages:

        page_number = page["page"]
        page_text = clean_text(page["text"])

        # Skip empty pages
        if not page_text:
            continue

        # Search for opinion keywords
        matched_keywords = find_opinion_keywords(page_text)

        if matched_keywords:

            removed_pages.append({
                "id": report_id,
                "page": page_number,
                "matched_keywords": " | ".join(matched_keywords),
                "page_length": len(page_text),
            })

        else:

            kept_pages.append(page_text)

    # Stitch remaining pages together
    final_text = "\n\n".join(kept_pages)

    final_text = clean_text(final_text)

    return final_text, removed_pages


# ============================================================
# 8. LOAD SELECTED DATASET CSV
# ============================================================

print("Loading selected dataset CSV...")

df = pd.read_csv(
    CSV_PATH,
    dtype=str,
    keep_default_na=False,
    encoding="utf-8-sig",
)

# Validate dataset splits
df["set"] = df["set"].str.strip().str.lower()

valid_sets = {"train", "val", "test"}

invalid_sets = set(df["set"]) - valid_sets

if invalid_sets:
    raise ValueError(
        f"Invalid dataset splits found: {invalid_sets}"
    )

df["modified"] = df["modified"].str.strip()

# ============================================================
# 9. PROCESS ALL REPORTS
# ============================================================

print(f"Found {len(df)} reports in CSV.")

datasets = {
    "train": [],
    "val": [],
    "test": [],
}

all_removed_pages = []
missing_markdown = []

for index, row in df.iterrows():

    report_id = row["id"].strip()

    markdown_path = MARKDOWN_DIR / f"{report_id}.md"

    print(
        f"[{index + 1}/{len(df)}] Processing {report_id}"
    )

    if not markdown_path.is_file():

        missing_markdown.append({
            "id": report_id,
            "expected_path": str(markdown_path),
        })

        continue

    # Process Markdown
    final_text, removed_pages = process_report(
        report_id,
        markdown_path,
    )

    all_removed_pages.extend(removed_pages)

    # Do not silently create empty training examples
    if not final_text.strip():

        print(
            f"WARNING: Report {report_id} has no text "
            "remaining after page removal."
        )

        continue

    # Convert modified label from 0/1 to Boolean
    modified = row["modified"] == "1"

    # Final JSONL record
    record = {
        "id": report_id,
        "text": final_text,
        "modified": modified,
    }

    # Assign report to the correct dataset split
    dataset_split = row["set"]

    datasets[dataset_split].append(record)


# ============================================================
# 10. SAVE THREE JSONL DATASETS
# ============================================================

output_names = {
    "train": "train.jsonl",
    "val": "validation.jsonl",
    "test": "test.jsonl",
}

for split, records in datasets.items():

    output_path = OUTPUT_DIR / output_names[split]

    with output_path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as outfile:

        for record in records:

            json_line = json.dumps(
                record,
                ensure_ascii=False,
            )

            outfile.write(json_line + "\n")

    print(
        f"Saved {len(records)} reports to {output_path}"
    )


# ============================================================
# 11. SAVE REMOVED PAGE AUDIT LOG
# ============================================================

removed_df = pd.DataFrame(
    all_removed_pages,
    columns=[
        "id",
        "page",
        "matched_keywords",
        "page_length",
    ],
)

removed_df.to_csv(
    REMOVED_PAGES_PATH,
    index=False,
    encoding="utf-8-sig",
)

print(
    f"\nRemoved page records: {len(removed_df)}"
)

print(
    f"Saved removal log to: {REMOVED_PAGES_PATH}"
)

# ============================================================
# 13. FINAL SUMMARY
# ============================================================

print("\n" + "=" * 50)
print("DATASET GENERATION COMPLETE")
print("=" * 50)

print(f"Reports in CSV:       {len(df)}")
print(f"Train reports:        {len(datasets['train'])}")
print(f"Validation reports:   {len(datasets['val'])}")
print(f"Test reports:         {len(datasets['test'])}")
print(f"Removed pages:        {len(all_removed_pages)}")
print(f"Missing Markdown:     {len(missing_markdown)}")

print("\nOutput directory:")
print(OUTPUT_DIR.resolve())
