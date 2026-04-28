from travel_data_platform.domain.alert import AlertCandidate


class AlertRuleEvaluator:
    def evaluate(
        self,
        current_price: int,
        currency: str,
        target_price: int | None,
        min_price_7d: int | None,
    ) -> list[AlertCandidate]:
        candidates: list[AlertCandidate] = []

        below_target = self._evaluate_below_target(
            current_price=current_price,
            currency=currency,
            target_price=target_price,
        )
        if below_target is not None:
            candidates.append(below_target)

        new_low_7d = self._evaluate_new_low_7d(
            current_price=current_price,
            currency=currency,
            min_price_7d=min_price_7d,
        )
        if new_low_7d is not None:
            candidates.append(new_low_7d)

        return candidates

    def _evaluate_below_target(
        self,
        current_price: int,
        currency: str,
        target_price: int | None,
    ) -> AlertCandidate | None:
        if target_price is None:
            return None

        if current_price > target_price:
            return None

        return AlertCandidate(
            alert_type="BELOW_TARGET",
            current_price=current_price,
            currency=currency,
            baseline_price=None,
            target_price=target_price,
            message=f"Current price {current_price} {currency} is below target price {target_price} {currency}.",
        )

    def _evaluate_new_low_7d(
        self,
        current_price: int,
        currency: str,
        min_price_7d: int | None,
    ) -> AlertCandidate | None:
        if min_price_7d is None:
            return None

        if current_price > min_price_7d:
            return None

        return AlertCandidate(
            alert_type="NEW_LOW_7D",
            current_price=current_price,
            currency=currency,
            baseline_price=min_price_7d,
            target_price=None,
            message=f"Current price {current_price} {currency} is the lowest price in the last 7 days.",
        )
