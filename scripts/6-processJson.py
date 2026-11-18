import json
from pathlib import Path
from html.parser import HTMLParser
from html import unescape

OUTPUT_DIR = Path('./data/ocr-output')
print(OUTPUT_DIR.absolute())

def extract_text(content_list):
    if isinstance(content_list, str):
        return content_list
    if not isinstance(content_list, list):
        return str(content_list)
    parts = []
    for item in content_list:
        if isinstance(item, dict):
            ct = item.get('type')
            cv = item.get('content', '')
            if ct == 'equation_inline':
                parts.append(f"${cv}$")
            elif isinstance(cv, (list, dict)):
                parts.append(extract_text(cv))
            else:
                parts.append(str(cv))
        elif isinstance(item, str):
            parts.append(item)
    return '\n'.join(parts)

def format_table(content_list):
    caption, body, footnote = [], '', []
    for item in content_list:
        if not isinstance(item, dict):
            continue
        ct = item.get('type')
        cv = item.get('content', '')
        if ct == 'table_caption':
            caption.append(extract_text(cv))
        elif ct == 'table_body':
            body = str(cv)
        elif ct == 'table_footnote':
            footnote.append(extract_text(cv))

    res = []
    if caption:
        res.append('**Table: ' + ' '.join(caption) + '**\n')
    if body:
        res.append(html_table_to_markdown(body))
    if footnote:
        res.append('\n*' + ' '.join(footnote) + '*')
    return '\n'.join(res)

def json_to_markdown(data, include_page_breaks=True, include_headers_footers=False):
    pages = data.get('pages', [])
    md_lines = []
    for p_idx, page in enumerate(pages):
        page_num = page.get('page_idx', p_idx) + 1
        page_content = []
        blocks = sorted(page.get('blocks', []), key=lambda b: b.get('index', 0))
        for b in blocks:
            b_type = b.get('type')
            # Omit headers/footers/page numbers to keep dataset clean for LLM
            if not include_headers_footers and b_type in ('header', 'footer', 'page_number', 'aside_text', 'image'):
                continue
            contents = b.get('content', [])
            if b_type == 'doc_title':
                t = extract_text(contents).strip()
                if t: page_content.append(f"# {t}\n")
            elif b_type == 'paragraph_title':
                t = extract_text(contents).strip()
                if t: page_content.append(f"## {t}\n")
            elif b_type == 'text':
                t = extract_text(contents).strip()
                if t: page_content.append(f"{t}\n")
            elif b_type == 'table':
                t_md = format_table(contents)
                if t_md: page_content.append(f"{t_md}\n")
            elif b_type == 'code':
                c = extract_text(contents).strip()
                if c: page_content.append(f"```\n{c}\n```\n")
            elif b_type == 'index':
                t = extract_text(contents).strip()
                if t: page_content.append(f"{t}\n")
            else:
                t = extract_text(contents).strip()
                if t: page_content.append(f"{t}\n")
        if page_content:
            if include_page_breaks and p_idx > 0:
                md_lines.append(f"\n<!-- Page {page_num} -->\n\n")
            md_lines.extend(page_content)
    return '\n'.join(md_lines)

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.current_row = None
        self.current_cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.current_row = []
        elif tag in ("td", "th") and self.current_row is not None:
            self.current_cell = []

    def handle_data(self, data):
        if self.current_cell is not None:
            self.current_cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.current_cell is not None:
            text = "".join(self.current_cell)
            text = " ".join(text.split())
            text = text.replace("|", r"\|")
            self.current_row.append(text)
            self.current_cell = None

        elif tag == "tr" and self.current_row is not None:
            self.rows.append(self.current_row)
            self.current_row = None


def html_table_to_markdown(html: str) -> str:
    """
    Convert an HTML table string into a Markdown table.
    The first row is treated as the header.
    """
    parser = TableParser()
    parser.feed(unescape(html))
    parser.close()

    rows = parser.rows

    if not rows:
        return ""

    # Normalize rows to have the same number of columns
    num_columns = max(len(row) for row in rows)

    rows = [
        row + [""] * (num_columns - len(row))
        for row in rows
    ]

    # Build Markdown table
    markdown_rows = []

    # Header
    markdown_rows.append(
        "| " + " | ".join(rows[0]) + " |"
    )

    # Separator
    markdown_rows.append(
        "| " + " | ".join(["---"] * num_columns) + " |"
    )

    # Data rows
    for row in rows[1:]:
        markdown_rows.append(
            "| " + " | ".join(row) + " |"
        )

    return "\n".join(markdown_rows)


# Scan all output folders
json_files = list(OUTPUT_DIR.glob('*/*.json'))
print(f"Found {len(json_files)} JSON files in {OUTPUT_DIR}")

converted_count = 0
for jf in json_files:
    md_path = Path("./data/md") / f"{jf.stem}.md"
    if md_path.exists() and md_path.stat().st_size > 0:
        continue
    try:
        with open(jf, 'r', encoding='utf-8') as f:
            data = json.load(f)
        md_text = json_to_markdown(data)
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_text)
        converted_count += 1
    except Exception as e:
        print(f"Error converting {jf.name}: {e}")

print(f"✨ Converted {converted_count} new JSON files to Markdown (.md)!")