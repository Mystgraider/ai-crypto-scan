class TradeLifecycle:

    def __init__(
        self,
        entry,
        stop_loss,
        tp1,
        tp2,
        tp3
    ):

        self.entry = entry
        self.stop_loss = stop_loss

        self.tp1 = tp1
        self.tp2 = tp2
        self.tp3 = tp3

        self.status = "OPEN"

        self.tp1_hit = False
        self.tp2_hit = False
        self.tp3_hit = False

    def update(
        self,
        price
    ):

        if self.status == "CLOSED":
            return self.status

        # Stop Loss

        if price <= self.stop_loss:

            self.status = "CLOSED"

            return self.status

        # TP1

        if (
            not self.tp1_hit and
            price >= self.tp1
        ):

            self.tp1_hit = True

            self.status = "TP1_HIT"

            self.stop_loss = self.entry

            return self.status

        # TP2

        if (
            self.tp1_hit and
            not self.tp2_hit and
            price >= self.tp2
        ):

            self.tp2_hit = True

            self.status = "TP2_HIT"

            return self.status

        # TP3

        if (
            self.tp2_hit and
            not self.tp3_hit and
            price >= self.tp3
        ):

            self.tp3_hit = True

            self.status = "CLOSED"

            return self.status

        return self.status
