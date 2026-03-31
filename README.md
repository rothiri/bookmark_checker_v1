# 📘 Bookmark Link Checker

A Python tool for analyzing, cleaning, and validating large Chrome bookmark collections.

It parses exported bookmarks, removes duplicates, checks links in parallel with retry and politeness controls, and generates multiple clean, importable outputs—including one that preserves your original folder structure without broken links.

---

## 🚀 Why this exists

If you’ve ever had thousands of bookmarks, you already know:

- Some are dead 💀  
- Some redirect somewhere unexpected  
- Some are duplicates  
- And finding anything useful becomes painful  

This tool turns that chaos into something usable again.

---

## ✨ Features

### 🔍 Bookmark Processing
- Parses Chrome bookmark HTML exports
- Supports nested folders
- Preserves title and add date

### 🧹 Deduplication
- Multiple modes:
  - `strict`
  - `basic`
  - `tracking_free`
  - `aggressive`
- URL normalization before comparison
- Safe duplicate removal

### ⚡ Parallel Link Checking
- Multi-threaded (`ThreadPoolExecutor`)
- Per-thread HTTP sessions (connection reuse)
- Configurable worker count

### ⏳ Politeness Controls
- Per-domain delay (prevents hammering sites)
- Shared throttling across threads

### 🔁 Retry & Backoff
- Retries transient failures automatically
- Exponential backoff + jitter
- Clean separation between:
  - check logic
  - retry logic

### 🧠 Smart Failure Detection
- HTTP errors
- soft 404s
- login walls (basic detection)
- content-based failures

---

## 📤 Outputs

### 📄 CSV (Full Results)
Detailed output for every URL:
- status
- final URL
- error type
- retry history

---

### 🌐 HTML – Valid Links (Flat)
Chrome-importable file with only working links.

---

### 🌍 HTML – Grouped by Domain
- Organized by domain
- Sorted oldest first
- Adds human-readable date prefixes

---

### 📁 HTML – Folder-Preserving (🔥)
Rebuilds your original folder structure **without broken links**.

- Keeps your organization intact  
- Removes dead bookmarks  
- Fully Chrome-importable  

---

### 📝 Markdown Report
Quick summary:
- total checked
- success vs failure
- top error types
- top failing domains

---
Flowchart TD
    A[Chrome Bookmarks HTML Export] --> B[parse_bookmarks.py<br/>Parse bookmarks + folder metadata]
    B --> C[dedupe.py<br/>Normalize + remove duplicates]
    C --> D[main.py orchestration]

    D --> E[ThreadPoolExecutor<br/>Parallel workers]
    E --> F[process_one_bookmark]

    F --> G[checks/politeness.py<br/>Per-domain delay]
    G --> H[checks/retry.py<br/>Retry with backoff + jitter]
    H --> I[checks/http_check.py<br/>Single HTTP check]

    I --> J[Worker result dict]
    J --> K[CheckResult model]

    K --> L[CSV Output<br/>Full results]
    K --> M[Valid bookmark list]

    M --> N[Flat HTML Export<br/>Chrome-importable]
    M --> O[Grouped by Domain Export<br/>Oldest first]
    M --> P[Folder-Preserving Export<br/>Rebuild original structure]
    K --> Q[Markdown Report<br/>Summary + failure counts]

## 🧱 Project Structure
bookmark_checker/
│
├── main.py
│
├── models.py
├── parse_bookmarks.py
├── dedupe.py
├── normalize.py
│
├── checks/
│ ├── http_check.py
│ ├── retry.py
│ └── politeness.py
│
├── writers/
│ └── folder_preserving.py
│
├── utils/
│ ├── dates.py
│ ├── logging.py
│ └── paths.py
│
└── config.py

Export bookmarks from Chrome
Chrome → Bookmarks → Bookmark Manager → Export Bookmarks


---

## ⚙️ Installation

```bash
git clone https://github.com/your-username/bookmark_checker.git
cd bookmark_checker

pip install -r requirements.txt