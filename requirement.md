# **Goal**

Write a Python program that reads an input CSV with three columns:

`id; phone; dob`

and produces an output CSV with the same three columns, where:

1. **id** is copied as-is,
2. **phone** is normalized to E.164 (e.g., +971501234567),
3. **dob** is normalized to ISO 8601 date (YYYY-MM-DD).

### Phone rules:
* If there’s no country code and the number looks local (starts with 0), assume UAE and prefix +971, dropping the local leading 0.


### Date rules
* Support numeric day/month swaps; for ambiguous all-numeric dates (e.g., 01/02/1990), assume day-first (DD/MM/YYYY) unless the month > 12 implies MM/DD/YYYY.
* Two-digit years: use a pivot of 25 → years 00–25 → 2000–2025; otherwise map to 1900–1999.

## Deliverables

**Script** (normalize_contacts.py) that:
1. Reads the provided CSV.
2. Writes normalized_contacts.csv.
3. Prints a short summary: number of rows processed, normalized, and any rows skipped with reasons.

**Dockerfile** 
That builds a runnable image containing the script.

**README.md**
Instructions for building/running the container.

