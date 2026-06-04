# Technical Debt

## PDF Chunking — ALL CAPS Heading Heuristic

**Area**: `api/app/rag/chunking.py` — `_pdf_units()`

**Issue**: PDF heading detection uses a fragile heuristic: lines with ≥70% uppercase alpha characters are treated as section headings.

**False positives**: acronyms (`FDA`, `PPE`), warnings (`CAUTION:`, `WARNING:`), table column headers, short COMPANY NAME lines.

**False negatives**: Title Case headings (`Intake Process` — 0% uppercased alpha — would be missed), numbered headings (`1. Intake Process`), multi-line headings split across PDF text lines, headings only distinguished by font size/weight (pypdf strips layout info).

**Proper fix**: Replace pypdf with `unstructured` library (`pip install unstructured`). Its `partition()` function detects headings by font metrics (size, weight, position) and returns typed elements (`Title`, `NarrativeText`, `ListItem`, `Table`). Would also unlock DOCX, PPTX, HTML, and (with OCR) image support.

**Priority**: Medium — current heuristic works for typical text-only PDFs with ALL CAPS headings, but will produce wrong chunks for Title Case or multi-line headings.

---

## Existing Items (from AGENTS.md)

| Area | Issue | Priority |
|------|-------|----------|
| State machine | Inline handler logic — should use pluggable handler registry | Medium |
| Policy engine | Default policies hardcoded, need validation + versioning | Low |
| Config.yaml | top_k:15 must be set manually on deploy | Low |
| Web widget | In-memory rate limit — needs Redis for multi-instance | Low |
