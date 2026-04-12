# Binance Remote Stop Loss Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Place a Binance-native `STOP_MARKET` protective stop with `MARK_PRICE` immediately after entry fill, and reconcile remote stop fills back into local trading state.

**Architecture:** `TradeEngine` remains the source of strategy intent and position bookkeeping, while `BinanceExchange` gains the parameter handling needed for protective `STOP_MARKET` orders. Local stop-loss logic stays as a fallback, but remote stop fills are detected during position sync so logs, cooldown, and trade records remain coherent.

**Tech Stack:** Python, pytest, Binance coin-m futures client, existing trade engine/exchange abstractions.

---

### Task 1: Add failing tests for protective stop placement

**Files:**
- Create: `tests/test_remote_stop_loss.py`
- Modify: `trade_module/trade_engine.py`
- Modify: `exchange_layer/binance_exchange.py`

**Step 1: Write the failing test**

Add a unit test showing that once a position exists and the exchange is Binance-like, calling the new stop-loss placement path submits a `STOP_MARKET` close-position order with `workingType='MARK_PRICE'` and stores the returned order id in `pos.sl_order_id`.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_remote_stop_loss.py::test_place_initial_stop_loss_order_uses_mark_price_close_position -v`
Expected: FAIL because the helper does not exist yet.

**Step 3: Write minimal implementation**

Add a `TradeEngine._place_initial_stop_loss_order()` helper and call it after position creation in `open_position()`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_remote_stop_loss.py::test_place_initial_stop_loss_order_uses_mark_price_close_position -v`
Expected: PASS

### Task 2: Add failing tests for Binance STOP_MARKET parameter handling

**Files:**
- Modify: `tests/test_remote_stop_loss.py`
- Modify: `exchange_layer/binance_exchange.py`

**Step 1: Write the failing test**

Add a unit test showing that `BinanceExchange.place_order()` removes `quantity` for `closePosition=true`, does not inject `timeInForce` for `STOP_MARKET`, preserves `workingType='MARK_PRICE'`, and derives hedge-mode `positionSide` as a closing order.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_remote_stop_loss.py::test_binance_stop_market_close_position_uses_expected_params -v`
Expected: FAIL because the current implementation still sends `quantity` and `timeInForce`.

**Step 3: Write minimal implementation**

Update `BinanceExchange.place_order()` and related order mapping so protective stop orders are encoded correctly.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_remote_stop_loss.py::test_binance_stop_market_close_position_uses_expected_params -v`
Expected: PASS

### Task 3: Add failing test for remote stop-fill reconciliation

**Files:**
- Modify: `tests/test_remote_stop_loss.py`
- Modify: `trade_module/trade_engine.py`

**Step 1: Write the failing test**

Add a unit test showing that when local state still has a position, exchange sync reports no position, and the tracked `sl_order_id` is already `FILLED`, the engine routes through stop-loss reconciliation instead of silently clearing local positions.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_remote_stop_loss.py::test_sync_positions_reconciles_filled_remote_stop_loss -v`
Expected: FAIL because sync currently just clears local positions.

**Step 3: Write minimal implementation**

Teach `sync_positions_from_exchange()` to inspect `sl_order_id`, detect a filled remote protective stop, and call the stop-loss close reconciliation path.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_remote_stop_loss.py::test_sync_positions_reconciles_filled_remote_stop_loss -v`
Expected: PASS

### Task 4: Run focused regression verification

**Files:**
- Test: `tests/test_remote_stop_loss.py`
- Test: `tests/test_binance_trade_excel_export.py`

**Step 1: Run the new focused tests**

Run: `pytest tests/test_remote_stop_loss.py -v`
Expected: PASS

**Step 2: Run an existing nearby regression suite**

Run: `pytest tests/test_binance_trade_excel_export.py -v`
Expected: PASS

**Step 3: Inspect diff**

Run: `git diff -- trade_module/trade_engine.py exchange_layer/binance_exchange.py tests/test_remote_stop_loss.py docs/plans/2026-04-11-binance-remote-stop-loss-design.md docs/plans/2026-04-11-binance-remote-stop-loss.md`
Expected: Only the intended remote stop-loss changes appear.
