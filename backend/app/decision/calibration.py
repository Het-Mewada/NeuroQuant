import math
from typing import List


class ProbabilityCalibrator:
    """
    Calibrates raw predictive heuristic scores into realistic empirical win probabilities
    and calculates mathematical expectancy net of friction.
    """

    def __init__(self):
        # Rolling historical outcomes: list of tuples (forecast_prob, actual_win: bool)
        self.history: List[tuple[float, bool]] = []

    def calibrate(self, raw_confidence: float) -> float:
        """
        Shrinks overconfident raw scores toward the prior mean (0.50).
        In non-stationary financial data, raw neural or heuristic scores are systematically overconfident.
        """
        # Conservative Bayesian shrinkage toward 0.50
        prior_mean = 0.50
        shrinkage_weight = 0.65  # 65% raw score, 35% base prior
        calibrated = (raw_confidence * shrinkage_weight) + (prior_mean * (1.0 - shrinkage_weight))
        return round(max(0.05, min(0.95, calibrated)), 4)

    def calculate_net_expectancy(
        self,
        calibrated_prob: float,
        entry_price: float,
        target_price: float,
        stop_loss_price: float,
        estimated_friction_points: float = 2.0
    ) -> float:
        """
        Computes expected value in R-multiples:
        E[R] = (P_win * Reward) - ((1 - P_win) * Risk) - Friction
        """
        reward = abs(target_price - entry_price)
        risk = max(0.05, abs(entry_price - stop_loss_price))

        p = calibrated_prob
        expected_rupees = (p * reward) - ((1.0 - p) * risk) - estimated_friction_points
        expected_r = expected_rupees / risk
        return round(expected_r, 3)

    def record_outcome(self, forecast_prob: float, won: bool):
        self.history.append((forecast_prob, won))
        if len(self.history) > 500:
            self.history.pop(0)

    def get_brier_score(self) -> float:
        if not self.history:
            return 0.25  # Uninformative baseline
        squared_errors = [
            (prob - (1.0 if won else 0.0)) ** 2
            for prob, won in self.history
        ]
        return round(sum(squared_errors) / len(squared_errors), 4)


calibrator = ProbabilityCalibrator()
