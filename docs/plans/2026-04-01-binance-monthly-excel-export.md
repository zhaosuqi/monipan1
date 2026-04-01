# Binance Monthly Excel Export Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a CLI export mode that connects to Binance live trading, fetches the last 30 days of trade history, and writes an Excel workbook with raw trades and a summary sheet.

**Architecture:** Extend the existing trade sync script instead of introducing a second entrypoint. Keep Binance I/O in the existing exchange and sync classes, and isolate Excel shaping, summary aggregation, and output-path generation into small pure helper functions so we can test them without real API access.

**Tech Stack:** Python, pandas, openpyxl, existing Binance CM futures connector, argparse

---

### Task 1: Prepare testable export helpers

**Files:**
- Modify: `scripts/sync_trades_from_binance.py`
- Test: `tests/test_binance_trade_excel_export.py`

**Step 1: Write the failing test**

Create tests for:

- converting sample Binance trades into raw export rows
- grouping summary metrics by `symbol` and `side`
- building a default output path under `data/exports/`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_binance_trade_excel_export.py -v`
Expected: FAIL because helper functions do not exist yet.

**Step 3: Write minimal implementation**

Add helper functions in `scripts/sync_trades_from_binance.py` for:

- time-window path generation
- raw trade normalization
- summary DataFrame construction

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_binance_trade_excel_export.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/sync_trades_from_binance.py tests/test_binance_trade_excel_export.py
git commit -m "feat: add trade export helpers"
```

### Task 2: Add Excel workbook writing

**Files:**
- Modify: `scripts/sync_trades_from_binance.py`
- Test: `tests/test_binance_trade_excel_export.py`

**Step 1: Write the failing test**

Add a test that writes a workbook to a temp path and asserts:

- file is created
- workbook contains `raw_trades` and `summary`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_binance_trade_excel_export.py -v`
Expected: FAIL because the workbook writer does not exist yet.

**Step 3: Write minimal implementation**

Implement workbook export using `pandas.ExcelWriter` and `openpyxl`, with basic formatting:

- bold header
- freeze top row
- auto width

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_binance_trade_excel_export.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/sync_trades_from_binance.py tests/test_binance_trade_excel_export.py
git commit -m "feat: add Binance trade Excel export writer"
```

### Task 3: Wire export mode into CLI

**Files:**
- Modify: `scripts/sync_trades_from_binance.py`

**Step 1: Write the failing test**

If CLI parsing remains hard to test directly, write a focused test for the export entry method instead:

- fetches the last 30 days window
- errors when API credentials are missing

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_binance_trade_excel_export.py -v`
Expected: FAIL because export mode is not yet wired.

**Step 3: Write minimal implementation**

Add:

- `--export-monthly-excel`
- `--output`
- export flow in `main()`
- explicit use of live exchange mode
- clear terminal success/error messages

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_binance_trade_excel_export.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/sync_trades_from_binance.py tests/test_binance_trade_excel_export.py
git commit -m "feat: add CLI for monthly Binance Excel export"
```

### Task 4: Verify end-to-end behavior

**Files:**
- Modify: `scripts/sync_trades_from_binance.py` if fixes are needed

**Step 1: Run automated tests**

Run: `pytest tests/test_binance_trade_excel_export.py -v`
Expected: PASS

**Step 2: Run the export command**

Run: `python scripts/sync_trades_from_binance.py --live --export-monthly-excel`
Expected: prints an absolute `.xlsx` path and generates the workbook

**Step 3: Inspect workbook structure**

Verify:

- `raw_trades` exists
- `summary` exists
- row counts look reasonable

**Step 4: Fix any issues and rerun verification**

Repeat the test and export commands until both pass.

**Step 5: Commit**

```bash
git add scripts/sync_trades_from_binance.py tests/test_binance_trade_excel_export.py docs/plans/2026-04-01-binance-monthly-excel-export-design.md docs/plans/2026-04-01-binance-monthly-excel-export.md
git commit -m "feat: export monthly Binance trades to Excel"
```
