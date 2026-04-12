# Binance Remote Stop Loss Design

**Goal:** After an entry order fills on Binance, immediately place a Binance-native `STOP_MARKET` protective stop order using `MARK_PRICE`, so real-time exchange protection takes priority over local minute-close stop detection.

**Context**

The current engine opens positions through the exchange layer, but stop loss is still enforced locally inside `process_tick()` by checking the latest bar and then sending a market close order. That is too slow for the new requirement because real protection must survive process lag and trigger intra-bar on Binance itself.

**Design**

1. After a position is created in `TradeEngine.open_position()`, compute the stop price with the existing `_calculate_stop_price()` logic.
2. If the active exchange is Binance live or testnet, submit a Binance `STOP_MARKET` order with:
   - opposite side of the position
   - `stopPrice` from `_calculate_stop_price()`
   - `workingType='MARK_PRICE'`
   - `closePosition=true`
3. Persist the returned exchange order id into `Position.sl_order_id`, and update stop-loss bookkeeping fields.
4. On any normal close path (take profit, drawdown close, manual/local stop close), cancel open related orders first, including the remote protective stop.
5. When Binance has already executed the protective stop and the next sync sees no position, detect that by querying `sl_order_id`; if the stop order is filled, reconcile it as a local stop-loss close instead of silently dropping the position.

**Implementation Notes**

- `BinanceExchange.place_order()` already accepts `**kwargs`, so the feature can be added without widening the base interface.
- `closePosition=true` stop orders must not force-send `quantity`, and `STOP_MARKET` must not force-send `timeInForce`.
- Hedge mode side inference must treat `closePosition=true` as a closing order so `positionSide` is derived correctly.
- Mock exchange behavior stays unchanged; remote protective stops are only placed on Binance.

**Risks**

- Real stop timing will diverge from historical backtest behavior because Binance `MARK_PRICE` can trigger intra-bar before a local minute close.
- If the process restarts, the current first version will not reconstruct the local `sl_order_id` linkage for pre-existing positions.
- Stop-order placement failures must surface clearly in logs so the operator can detect an unprotected position.
