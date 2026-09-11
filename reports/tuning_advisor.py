"""Phase 2D-C — evidence-based tuning advisor.

This module converts reliable historical calibration evidence into a review
recommendation. It is intentionally REPORT_ONLY: it never mutates strategy
weights, thresholds, confidence formulas, grade rules, or scanner decisions.

Important limitation: current signal logs store aggregate AI rank/confidence,
not per-component score contributions. Therefore this advisor can identify
whether aggregate score separation merits investigation, but it cannot
attribute that separation to individual model components.
"""

from reports.calibration_report import CalibrationReport

DEFAULT_MIN_SAMPLE = 20
DEFAULT_MIN_NET_R_GAP = 2.0
DEFAULT_MIN_WIN_RATE_GAP_PCT = 10.0


class TuningAdvisor:
    """Produce a conservative, evidence-gated tuning recommendation."""

    def __init__(
        self,
        signals=None,
        min_sample=DEFAULT_MIN_SAMPLE,
        min_net_r_gap=DEFAULT_MIN_NET_R_GAP,
        min_win_rate_gap_pct=DEFAULT_MIN_WIN_RATE_GAP_PCT,
    ):
        self.report = CalibrationReport(signals=signals, min_sample=min_sample)
        self.min_net_r_gap = float(min_net_r_gap)
        self.min_win_rate_gap_pct = float(min_win_rate_gap_pct)

    def compute(self):
        result = self.report.compute()
        ai = result["interpretation"]["ai_rank_score"]
        confidence = result["interpretation"]["confidence"]
        warnings = list(result["warnings"])

        base = {
            "evidence": result["evidence"],
            "warnings": warnings,
            "scope": result["scope"],
            "guardrail": (
                "REPORT_ONLY: no AI weights, confidence formula, thresholds, "
                "grade rules, or scanner entry rules are changed."
            ),
        }

        if not ai["reliable"] or not confidence["reliable"]:
            return {
                **base,
                "ready": False,
                "recommendation": {
                    "action": "NO_TUNING",
                    "reason": "Reliable AI and confidence calibration evidence is not yet available.",
                },
                "comparison": None,
                "attribution": {
                    "available": False,
                    "note": "Aggregate score outcomes are logged, but per-component score contributions are not stored.",
                },
            }

        strongest = ai["strongest"]
        weakest = ai["weakest"]
        net_r_gap = round(strongest["net_r"] - weakest["net_r"], 4)
        win_rate_gap = round(strongest["win_rate_pct"] - weakest["win_rate_pct"], 2)

        # Thresholds are strict: a gap must be greater than the configured
        # minimum to justify investigation. Exactly-at-threshold evidence is
        # treated as insufficient separation, avoiding borderline tuning.
        meaningful = (
            net_r_gap > self.min_net_r_gap
            or win_rate_gap > self.min_win_rate_gap_pct
        )

        action = "INVESTIGATE_COMPONENTS" if meaningful else "NO_TUNING"
        reason = (
            "Reliable aggregate score separation is large enough to justify component-level investigation."
            if meaningful
            else "Reliable aggregate score separation does not meet the evidence threshold for further tuning work."
        )

        return {
            **base,
            "ready": True,
            "recommendation": {"action": action, "reason": reason},
            "comparison": {
                "strongest_ai_bucket": strongest["bucket"],
                "weakest_ai_bucket": weakest["bucket"],
                "net_r_gap": net_r_gap,
                "win_rate_gap_pct": win_rate_gap,
                "min_net_r_gap": self.min_net_r_gap,
                "min_win_rate_gap_pct": self.min_win_rate_gap_pct,
            },
            "attribution": {
                "available": False,
                "note": "Aggregate score outcomes are logged, but per-component score contributions are not stored.",
            },
        }

    def render_text(self):
        result = self.compute()
        rec = result["recommendation"]
        lines = [
            "Phase 2D-C Evidence-Based Tuning Advisor",
            "==========================================",
            f"Ready: {result['ready']}",
            f"Action: {rec['action']}",
            f"Reason: {rec['reason']}",
        ]
        if result["comparison"]:
            comparison = result["comparison"]
            lines.extend(
                [
                    "",
                    "Aggregate evidence",
                    f"  Strongest AI bucket: {comparison['strongest_ai_bucket']}",
                    f"  Weakest AI bucket: {comparison['weakest_ai_bucket']}",
                    f"  Net R gap: {comparison['net_r_gap']}",
                    f"  Win-rate gap: {comparison['win_rate_gap_pct']}pp",
                ]
            )
        lines.extend(
            [
                "",
                "Attribution",
                f"  Available: {result['attribution']['available']}",
                f"  Note: {result['attribution']['note']}",
            ]
        )
        if result["warnings"]:
            lines.append("")
            lines.append("Warnings")
            lines.extend(f"  - {item}" for item in result["warnings"])
        lines.extend(["", result["guardrail"]])
        return "\n".join(lines)


if __name__ == "__main__":
    print(TuningAdvisor().render_text())
