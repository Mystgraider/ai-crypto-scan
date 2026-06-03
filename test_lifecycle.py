from lifecycle_engine import (
    TradeLifecycle
)

trade = TradeLifecycle(

    entry=100,

    stop_loss=95,

    tp1=105,

    tp2=110,

    tp3=120
)

print(
    trade.update(103)
)

print(
    trade.update(106)
)

print(
    trade.update(111)
)

print(
    trade.update(121)
)
