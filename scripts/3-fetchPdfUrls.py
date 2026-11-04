
import pandas as pd
from playwright.sync_api import sync_playwright
import time

INPUT_CSV = "selected_dataset_list.csv"
OUTPUT_CSV = "report_pdf_urls.csv"

df = pd.read_csv(INPUT_CSV)

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    context = browser.new_context()
    page = context.new_page()

    for index, row in df.iterrows():
        page_url = row["link_vnreport"]
        report_id = row["id"]
        report_set = row["set"]
        modified = row["modified"]

        print(f"[{index + 1}/{len(df)}] Processing {report_id}")

        pdf_urls = set()

        # Listen to all network requests
        def capture_request(request):
            url = request.url.lower()

            if ".pdf" in url:
                pdf_urls.add(request.url)

        context.on("request", capture_request)

        try:
            page.goto(
                page_url,
                wait_until="domcontentloaded",
                timeout=30000
            )

            # Allow the PDF viewer time to load
            page.wait_for_timeout(3000)

        except Exception as e:
            print(f"Error: {e}")

        finally:
            context.remove_listener("request", capture_request)

        for pdf_url in pdf_urls:
            print("PDF found:", pdf_url)

        results.append({
            "id": report_id,
            "pdf_url": ";".join(pdf_urls) if pdf_urls else None,
            "set": report_set,
            "modified": modified
        })

        # Avoid sending requests too quickly
        time.sleep(1)

    browser.close()

# Save results
output_df = pd.DataFrame(results)
output_df.to_csv(
    OUTPUT_CSV,
    index=False,
    encoding="utf-8-sig"
)

print(f"\nCompleted! Saved to {OUTPUT_CSV}")
