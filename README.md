# 📘 Bookmark Link Checker

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Status](https://img.shields.io/badge/status-active-success)
![License](https://img.shields.io/badge/license-MIT-green)
![Concurrency](https://img.shields.io/badge/concurrency-multithreaded-orange)
![Resilience](https://img.shields.io/badge/retry-backoff%20%2B%20jitter-blueviolet)

A Python tool for analyzing, cleaning, and validating large Chrome bookmark collections.

It parses exported bookmarks, removes duplicates, checks links in parallel with retry and politeness controls, and generates clean, importable outputs—including one that preserves your original folder structure without broken links.

---

## 🚀 What this solves

If you’ve ever had thousands of bookmarks, you already know:

- Some are dead 💀  
- Some redirect somewhere unexpected  
- Some are duplicates  
- And finding anything useful becomes painful  

This tool turns that chaos into something usable again.

---

## ⚡ Quick Example

```bash
python -m bookmark_checker.main \
  --bookmarks bookmarks.html \
  --out results.csv \
  --workers 10 \
  --dedupe-mode aggressive

## 💼 Engineering Highlights

- Multi-threaded processing with controlled concurrency
- Retry/backoff strategy with jitter
- Domain-level rate limiting (politeness)
- Modular architecture with clear separation of concerns
- Multiple output pipelines from a single validation pass

## 🧠 Why this project is interesting

This project focuses on real-world engineering challenges:

- Handling unreliable external systems (websites)
- Balancing concurrency with politeness constraints
- Designing retryable, resilient workflows
- Transforming messy data into structured outputs

It’s not just a script—it’s a small data processing pipeline.

## 📚 Documentation

- [Developer Guide](docs/DEVELOPER_GUIDE.md)