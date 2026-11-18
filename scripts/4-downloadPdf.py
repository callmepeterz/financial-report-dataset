import csv
import time
from pathlib import Path

import requests


# Paths
CSV_PATH = Path("data/report_pdf_urls.csv")
OUTPUT_DIR = Path("pdf")

# Download settings
TIMEOUT = 60
MAX_RETRIES = 3
CHUNK_SIZE = 1024 * 64

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def download_pdf(session, report_id, url):
    """Download one PDF and save it as pdf/{id}.pdf."""

    output_path = OUTPUT_DIR / f"{report_id}.pdf"
    temp_path = OUTPUT_DIR / f"{report_id}.pdf.part"

    # Skip existing valid PDFs
    if output_path.exists() and output_path.stat().st_size > 0:
        with output_path.open("rb") as f:
            if f.read(5) == b"%PDF-":
                print(f"[SKIP] {report_id}: already downloaded")
                return True

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(
                f"[DOWNLOAD] {report_id} "
                f"(attempt {attempt}/{MAX_RETRIES})"
            )

            with session.get(
                url,
                timeout=TIMEOUT,
                stream=True,
            ) as response:

                response.raise_for_status()

                with temp_path.open("wb") as f:
                    for chunk in response.iter_content(
                        chunk_size=CHUNK_SIZE
                    ):
                        if chunk:
                            f.write(chunk)

            # Validate PDF signature
            with temp_path.open("rb") as f:
                signature = f.read(5)

            if signature != b"%PDF-":
                temp_path.unlink(missing_ok=True)
                raise ValueError("Downloaded file is not a valid PDF")

            # Rename only after successful download
            temp_path.replace(output_path)

            size_mb = output_path.stat().st_size / (1024 * 1024)

            print(
                f"[SUCCESS] {report_id}: "
                f"{size_mb:.2f} MB"
            )

            return True

        except Exception as e:
            print(
                f"[ERROR] {report_id}: {e}"
            )

            temp_path.unlink(missing_ok=True)

            if attempt < MAX_RETRIES:
                time.sleep(2 * attempt)

    print(f"[FAILED] {report_id}")
    return False


def main():
    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"CSV file not found: {CSV_PATH}"
        )

    successful = 0
    failed = []

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0"
    })

    with CSV_PATH.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as csv_file:

        reader = csv.DictReader(csv_file)

        for row in reader:
            report_id = row["id"].strip()
            url = row["pdf_url"].strip()

            if not report_id or not url:
                print(f"[SKIP] Invalid row: {row}")
                continue

            if download_pdf(session, report_id, url):
                successful += 1
            else:
                failed.append(report_id)

    session.close()

    print("\n" + "=" * 45)
    print("DOWNLOAD SUMMARY")
    print("=" * 45)
    print(f"Successful: {successful}")
    print(f"Failed:     {len(failed)}")

    if failed:
        print("\nFailed report IDs:")
        for report_id in failed:
            print(f"- {report_id}")

        print("\nYou can rerun the script to retry failed downloads.")


if __name__ == "__main__":
    main()
