# 🛠 Developer Guide

This guide explains how the Bookmark Link Checker is structured, how data flows through the system, and how to safely extend or modify functionality.

---

## 🧠 Overview

This project is a modular pipeline for:

1. Parsing Chrome bookmark exports
2. Deduplicating URLs
3. Checking links in parallel with retry and politeness controls
4. Classifying results
5. Generating multiple output formats

The system is designed for **resilience, scalability, and extensibility**.

---

## 🧱 Project Layout

```text
bookmark_checker/
│
├── main.py                  # Orchestrates the pipeline
├── models.py                # Bookmark and CheckResult models
├── parse_bookmarks.py       # Parses Chrome bookmark HTML
├── dedupe.py                # Deduplication logic
├── normalize.py             # URL normalization
│
├── checks/
│   ├── http_check.py        # Single HTTP request (no retry)
│   ├── retry.py             # Retry logic (backoff + jitter)
│   └── politeness.py        # Per-domain delay
│
├── writers/
│   └── folder_preserving.py # Rebuilds folder structure
│
├── utils/
│   ├── dates.py
│   ├── logging.py
│   └── paths.py
│
└── config.py                # Config handling
```
## 🔄 Data Flow

```text
Chrome Bookmarks HTML
        ↓
parse_bookmarks.py
        ↓
List[Bookmark]
        ↓
dedupe.py
        ↓
Filtered List[Bookmark]
        ↓
ThreadPoolExecutor (parallel workers)
        ↓
process_one_bookmark()
        ↓
dict (raw result)
        ↓
CheckResult (model)
        ↓
├── CSV Output (all results)
├── Markdown Report (summary)
└── Valid Bookmarks (filtered subset)
        ↓
├── Flat HTML Export
├── Grouped-by-Domain Export
└── Folder-Preserving Export
```
### Notes

- Workers process one bookmark at a time and return a raw dictionary
- The main pipeline converts results into `CheckResult` objects
- Valid bookmarks are reused across multiple output writers
## 🏗 Data Flow Diagram

```mermaid
flowchart TD
    A[Chrome bookmarks export<br/>bookmarks.html] --> B[parse_bookmarks.py<br/>parse_bookmarks_html()]
    B --> C[List[Bookmark]]
    C --> D[dedupe.py<br/>dedupe_bookmarks()]
    D --> E[Deduped List[Bookmark] + stats]
    E --> F[main.py<br/>pipeline orchestration]

    F --> G[ThreadPoolExecutor]
    G --> H[process_one_bookmark()]

    H --> I[should_skip_url()]
    I --> J[checks/politeness.py<br/>polite_wait_domain()]
    J --> K[get_session()<br/>per-thread requests.Session]
    K --> L[checks/retry.py<br/>check_url_with_retries()]
    L --> M[checks/http_check.py<br/>check_url_once()]

    M --> N[raw worker dict]
    N --> O[models.py<br/>CheckResult.from_worker_dict()]
    O --> P[CheckResult]

    P --> Q[CSV writer<br/>full results]
    P --> R[valid_bookmarks list]
    P --> S[error counters / domain counters]

    R --> T[write_chrome_bookmarks_html()<br/>flat valid export]
    R --> U[write_valid_grouped_by_domain()<br/>grouped export]
    R --> V[writers/folder_preserving.py<br/>write_folder_preserving_valid_bookmarks_html()]

    S --> W[write_report_md()<br/>Markdown summary]

    F --> X[utils/paths.py<br/>derive_output_paths()]
    F --> Y[config.py<br/>defaults + YAML + CLI merge]
    U --> Z[utils/dates.py<br/>human_date_from_add_date()]
```
### Diagram Notes

- `parse_bookmarks.py` converts exported Chrome bookmark HTML into `Bookmark` objects
- `dedupe.py` removes duplicates before any network calls happen
- each worker processes one bookmark, applies skip rules, politeness delays, retries, and a single HTTP check
- worker output is converted into a `CheckResult` in `main.py`
- successful results are reused across multiple export writers

## ⚙️ Local Setup

### 1. Create a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt

python -m bookmark_checker.main \
  --bookmarks bookmarks.html \
  --out results.csv