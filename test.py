#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Job scraping script for theatre/media administrative roles across all job boards.

This script searches for two terms: "theatre administrative" and "media administrative".
It queries every job board available in the `jobspy` package for both New York City
and Boston, filters results by salary (hourly ≥ $28/hr or annual ≥ $50,000), removes
duplicates, writes the combined output to `jobs.csv`, and uploads the data to a Google
Sheet (if credentials are available).
"""

import os
import pathlib
import datetime
import pandas as pd
from dotenv import load_dotenv
from jobspy import scrape_jobs
from jobspy.model import CompensationInterval, Site
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Load environment variables
load_dotenv()

# Configuration
SEARCH_TERMS = ["theatre administrative", "media administrative"]
LOCATIONS = ["New York, NY", "Boston, MA"]
RESULTS_WANTED = 30
HOURS_OLD = 72
COUNTRY_INDEED = "USA"
# Use all sites defined in jobspy.model.Site
ALL_SITES = ["indeed", "linkedin", "zip_recruiter", "glassdoor"]


# Helper: convert a row's minimum salary to an annual amount
def annual_min(row: pd.Series) -> float | None:
    amount = row.get("min_amount")
    if amount is None:
        return None
    interval = row.get("interval")
    if interval == CompensationInterval.HOURLY.value:
        return amount * 2080
    if interval == CompensationInterval.DAILY.value:
        return amount * 260
    if interval == CompensationInterval.WEEKLY.value:
        return amount * 52
    if interval == CompensationInterval.MONTHLY.value:
        return amount * 12
    if interval == CompensationInterval.YEARLY.value:
        return amount
    return None

def scrape_and_collect() -> pd.DataFrame:
    all_jobs = pd.DataFrame()
    for term in SEARCH_TERMS:
        for loc in LOCATIONS:
            print(f"Searching for '{term}' in {loc}…")
            try:
                jobs = scrape_jobs(
                    site_name=ALL_SITES,
                    search_term=term,
                    location=loc,
                    results_wanted=RESULTS_WANTED,
                    hours_old=HOURS_OLD,
                    country_indeed=COUNTRY_INDEED,
                )
                if jobs is not None and not jobs.empty:
                    all_jobs = pd.concat([all_jobs, jobs], ignore_index=True)
            except Exception as e:
                print(f"❌ Error scraping {term} in {loc}: {e}")
    return all_jobs

def filter_jobs(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["annual_min_salary"] = df.apply(annual_min, axis=1)
    df = df[df["annual_min_salary"] >= 50000]
    df = df.drop(columns=["annual_min_salary"], errors="ignore")
    # Drop duplicates based on the job title and the URL column used by jobspy
    # Drop duplicates based on the job title and the URL column used by jobspy
    # The scraped dataframe uses the column name `JOB_URL` for the link.
    # If for some reason the column is named `url`, fall back to that.
    url_col = "JOB_URL" if "JOB_URL" in df.columns else ("url" if "url" in df.columns else None)
    if url_col:
        df = df.drop_duplicates(subset=["title", url_col])
    else:
        # If no URL column is available, rely on title only
        df = df.drop_duplicates(subset=["title"])
    # The scraped dataframe uses the column name `JOB_URL` for the link.
    # If for some reason the column is named `url`, fall back to that.
    url_col = "JOB_URL" if "JOB_URL" in df.columns else ("url" if "url" in df.columns else None)
    if url_col:
        df = df.drop_duplicates(subset=["title", url_col])
    else:
        # If no URL column is available, rely on title only
        df = df.drop_duplicates(subset=["title"])
    return df

def write_csv(df: pd.DataFrame, path: str = "jobs.csv"):
    df.to_csv(path, index=False)
    print(f"✅ Saved {len(df)} jobs to {path}")

def upload_to_sheet(df: pd.DataFrame):
    if df.empty:
        print("⚠️ No jobs to upload – skipping Google Sheet")
        return
    creds_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not creds_file:
        print("⚠️ GOOGLE_SERVICE_ACCOUNT_JSON not set – skipping Google Sheet upload")
        return
    key_path = pathlib.Path(creds_file)
    if not key_path.is_absolute():
        key_path = pathlib.Path(__file__).parent / key_path
    if not key_path.is_file():
        print(f"⚠️ Service account key not found at {key_path}")
        return
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(str(key_path), scope)
    client = gspread.authorize(creds)
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    sh = client.open_by_key(sheet_id)
    sheet_name = (
        f"Scrape {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-5))).strftime('%Y-%m-%d %I:%M %p')}"
    )
    try:
        worksheet = sh.add_worksheet(title=sheet_name, rows="1000", cols="20")
    except gspread.exceptions.APIError:
        worksheet = sh.worksheet(sheet_name)
    worksheet.clear()
    worksheet.append_row(list(df.columns))
    rows_to_append = []
    for _, row in df.iterrows():
        cleaned = [None if pd.isna(v) else v for v in row.tolist()]
        rows_to_append.append(cleaned)
    if rows_to_append:
        worksheet.append_rows(rows_to_append, value_input_option="RAW")
    print(f"✅ Uploaded {len(df)} rows to Google Sheet '{sheet_name}'")

def main():
    # For quick testing, load a pre‑existing CSV instead of scraping
    # jobs = scrape_and_collect()
    # if jobs.empty:
    #     print("⚠️ No jobs found.")
    #     return
    # jobs = filter_jobs(jobs)
    # jobs["search_date"] = datetime.datetime.utcnow().isoformat()
    # write_csv(jobs)
    # upload_to_sheet(jobs)
    jobs = pd.read_csv("jobs.csv")
    if jobs.empty:
        print("⚠️ jobs.csv is empty – nothing to upload.")
        return
    # Ensure the column used for deduplication exists
    if "JOB_URL" not in jobs.columns and "url" in jobs.columns:
        jobs = jobs.rename(columns={"url": "JOB_URL"})
    jobs = filter_jobs(jobs)
    # Convert column names to title case for consistency
    jobs.columns = jobs.columns.str.replace("_", " ", regex=True).str.title()
    jobs["Search Date"] = datetime.datetime.now().strftime("%m/%d/%Y")
    upload_to_sheet(jobs)

if __name__ == "__main__":
    main()


