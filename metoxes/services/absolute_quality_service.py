from __future__ import annotations

import math


RELATIVE_WEIGHT = 0.60
ABSOLUTE_WEIGHT = 0.40

# Βάρη μέσα στο Absolute Quality Score.
ABSOLUTE_METRIC_WEIGHTS = {
    "fcf_yield": 0.25,
    "roic": 0.25,
    "fcf_growth": 0.20,
    "forward_revenue_growth": 0.15,
    "forward_eps_growth": 0.15,
}

# Ελάχιστη κάλυψη δεδομένων για να εφαρμοστεί το 60/40.
# 0.50 = πρέπει να υπάρχει τουλάχιστον το 50% του
# συνολικού absolute weight. Αλλιώς κρατάμε μόνο το
# relative score ώστε να μην παράγουμε ψευδή ακρίβεια.
MIN_ABSOLUTE_COVERAGE = 0.50


def _safe_float(value):
    if value in (None, ""):
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(number) or math.isinf(number):
        return None

    return number


def _clamp(value, minimum=0.0, maximum=100.0):
    return max(
        minimum,
        min(maximum, value),
    )


def _piecewise_score(value, points):
    """
    Μετατρέπει ένα πραγματικό metric σε score 0-100.

    points:
        [(x1, score1), (x2, score2), ...]

    Αν το value είναι ανάμεσα σε δύο σημεία,
    γίνεται γραμμική παρεμβολή.
    """
    number = _safe_float(value)

    if number is None:
        return None

    if number <= points[0][0]:
        return float(points[0][1])

    if number >= points[-1][0]:
        return float(points[-1][1])

    for index in range(len(points) - 1):
        x1, s1 = points[index]
        x2, s2 = points[index + 1]

        if x1 <= number <= x2:
            if x2 == x1:
                return float(s2)

            ratio = (
                (number - x1)
                / (x2 - x1)
            )

            score = (
                s1
                + ratio * (s2 - s1)
            )

            return round(
                _clamp(score),
                2,
            )

    return None


def score_fcf_yield(value):
    """
    Absolute FCF Yield score.

    <= 0%  -> 0
    2%     -> 25
    4%     -> 45
    6%     -> 65
    8%     -> 85
    >=10%  -> 100
    """
    return _piecewise_score(
        value,
        [
            (0, 0),
            (2, 25),
            (4, 45),
            (6, 65),
            (8, 85),
            (10, 100),
        ],
    )


def score_roic(value):
    """
    Absolute ROIC score.

    <= 0%  -> 0
    5%     -> 20
    10%    -> 45
    15%    -> 70
    20%    -> 90
    >=25%  -> 100
    """
    return _piecewise_score(
        value,
        [
            (0, 0),
            (5, 20),
            (10, 45),
            (15, 70),
            (20, 90),
            (25, 100),
        ],
    )


def score_fcf_growth(value):
    """
    Absolute FCF Growth score.

    Το growth γίνεται capped πρακτικά στο 30%:
    +300%, +1000% κ.λπ. δεν μπορούν να δώσουν >100.

    <= -25% -> 0
    0%      -> 30
    5%      -> 45
    10%     -> 60
    20%     -> 80
    >=30%   -> 100
    """
    return _piecewise_score(
        value,
        [
            (-25, 0),
            (0, 30),
            (5, 45),
            (10, 60),
            (20, 80),
            (30, 100),
        ],
    )


def score_forward_revenue_growth(value):
    """
    Absolute Forward Revenue Growth score.

    <= -10% -> 0
    0%      -> 20
    5%      -> 45
    10%     -> 65
    15%     -> 82
    >=20%   -> 100
    """
    return _piecewise_score(
        value,
        [
            (-10, 0),
            (0, 20),
            (5, 45),
            (10, 65),
            (15, 82),
            (20, 100),
        ],
    )


def score_forward_eps_growth(value):
    """
    Absolute Forward EPS Growth score.

    <= -20% -> 0
    0%      -> 20
    5%      -> 40
    10%     -> 60
    20%     -> 80
    >=30%   -> 100
    """
    return _piecewise_score(
        value,
        [
            (-20, 0),
            (0, 20),
            (5, 40),
            (10, 60),
            (20, 80),
            (30, 100),
        ],
    )


ABSOLUTE_SCORERS = {
    "fcf_yield": score_fcf_yield,
    "roic": score_roic,
    "fcf_growth": score_fcf_growth,
    "forward_revenue_growth":
        score_forward_revenue_growth,
    "forward_eps_growth":
        score_forward_eps_growth,
}


def _calculate_absolute_score(row):
    weighted_total = 0.0
    available_weight = 0.0

    component_scores = {}

    for metric, weight in ABSOLUTE_METRIC_WEIGHTS.items():
        scorer = ABSOLUTE_SCORERS[metric]
        metric_score = scorer(
            row.get(metric)
        )

        component_scores[
            f"absolute_{metric}_score"
        ] = metric_score

        if metric_score is None:
            continue

        weighted_total += (
            metric_score * weight
        )

        available_weight += weight

    if available_weight <= 0:
        absolute_score = None
        coverage = 0.0
    else:
        # Re-normalization μόνο στα διαθέσιμα metrics.
        absolute_score = round(
            weighted_total
            / available_weight,
            2,
        )

        coverage = round(
            available_weight
            / sum(
                ABSOLUTE_METRIC_WEIGHTS.values()
            ),
            4,
        )

    return (
        absolute_score,
        coverage,
        component_scores,
    )


def add_absolute_quality_scores(scores):
    """
    Παίρνει το ήδη υπάρχον final_score ως Relative Score
    και δημιουργεί:

        Final Score =
            60% Relative Score
            + 40% Absolute Quality Score

    Αν η absolute κάλυψη είναι < 50%, δεν εφαρμόζουμε
    το 60/40 και κρατάμε προσωρινά το Relative Score.
    """
    if not scores:
        return scores

    result = [
        dict(row)
        for row in scores
    ]

    for row in result:
        relative_score = _safe_float(
            row.get("final_score")
        )

        (
            absolute_score,
            absolute_coverage,
            component_scores,
        ) = _calculate_absolute_score(
            row
        )

        row.update(
            component_scores
        )

        row["relative_score"] = (
            round(relative_score, 2)
            if relative_score is not None
            else None
        )

        row["absolute_score"] = (
            absolute_score
        )

        row["absolute_coverage"] = round(
            absolute_coverage * 100,
            2,
        )

        if relative_score is None:
            row["final_score"] = None
            row["score_mode"] = (
                "no_relative_score"
            )
            continue

        if (
            absolute_score is None
            or absolute_coverage
            < MIN_ABSOLUTE_COVERAGE
        ):
            row["final_score"] = round(
                relative_score,
                2,
            )

            row["score_mode"] = (
                "relative_only"
            )
            continue

        row["final_score"] = round(
            relative_score
            * RELATIVE_WEIGHT
            + absolute_score
            * ABSOLUTE_WEIGHT,
            2,
        )

        row["score_mode"] = (
            "relative_60_absolute_40"
        )

    return result
