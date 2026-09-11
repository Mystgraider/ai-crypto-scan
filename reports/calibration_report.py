"""Phase 2D-B2 — calibration reporting and interpretation.

Turns the read-only Phase 2D-B1 measurements into a compact report for humans
and automation. This module does not tune weights, thresholds, confidence,
grade rules, or scanner decisions.
"""

from reports.calibration_engine import CalibrationEngine


class CalibrationReport:
    """Build evidence-based calibration reporting from historical signals."""

    def __init__(self, signals=None, min_sample=20):
        self.engine = CalibrationEngine(signals=signals, min_sample=min_sample)

    @staticmethod
    def _reliable_items(bucket_map):
        return [
            (label, data)
            for label, data in bucket_map.items()
            if data and data.get("reliable")
        ]

    @classmethod
    def _interpret_buckets(cls, bucket_map, metric="net_r"):
        reliable = cls._reliable_items(bucket_map)
        if not reliable:
            return {
                "reliable": False,
                "strongest": None,
                "weakest": None,
                "note": "No bucket has enough resolved samples for a reliable comparison.",
            }

        strongest = max(reliable, key=lambda item: item[1].get(metric, 0.0))
        weakest = min(reliable, key=lambda item: item[1].get(metric, 0.0))
        return {
            "reliable": True,
            "strongest": {"bucket": strongest[0], **strongest[1]},
            "weakest": {"bucket": weakest[0], **weakest[1]},
            "note": "Comparisons are descriptive only; no strategy changes are implied.",
        }

    @classmethod
    def _confidence_interpretation(cls, bucket_map):
        reliable = cls._reliable_items(bucket_map)
        if not reliable:
            return {
                "reliable": False,
                "most_overconfident": None,
                "most_underconfident": None,
                "note": "No confidence bucket has enough resolved samples for a reliable comparison.",
            }

        over = max(reliable, key=lambda item: item[1].get("mean_predicted_pct", 0.0) - item[1].get("win_rate_pct", 0.0))
        under = min(reliable, key=lambda item: item[1].get("mean_predicted_pct", 0.0) - item[1].get("win_rate_pct", 0.0))
        return {
            "reliable": True,
            "most_overconfident": {"bucket": over[0], **over[1]},
            "most_underconfident": {"bucket": under[0], **under[1]},
            "note": "Calibration error is diagnostic only because confidence is not yet a calibrated probability.",
        }

    @staticmethod
    def _grade_interpretation(grade_map):
        reliable = [
            (grade, data)
            for grade, data in grade_map.items()
            if data and data.get("reliable")
        ]
        if not reliable:
            return {
                "reliable": False,
                "strongest": None,
                "weakest": None,
                "note": "No grade has enough resolved samples for a reliable comparison.",
            }

        strongest = max(reliable, key=lambda item: item[1].get("net_r", 0.0))
        weakest = min(reliable, key=lambda item: item[1].get("net_r", 0.0))
        return {
            "reliable": True,
            "strongest": {"grade": strongest[0], **strongest[1]},
            "weakest": {"grade": weakest[0], **weakest[1]},
            "note": "Grade comparisons include legacy resolved history when grade and realized R are available.",
        }

    def compute(self):
        report = self.engine.compute()
        summary = self.engine.summary()

        ai_interpretation = self._interpret_buckets(report["ai_rank_score"])
        confidence_interpretation = self._confidence_interpretation(report["confidence"])
        grade_interpretation = self._grade_interpretation(report["grade"])

        evidence = []
        warnings = list(summary["warnings"])

        if ai_interpretation["strongest"]:
            evidence.append(
                "Strongest reliable AI bucket by Net R: "
                f"{ai_interpretation['strongest']['bucket']}"
            )
        if ai_interpretation["weakest"]:
            evidence.append(
                "Weakest reliable AI bucket by Net R: "
                f"{ai_interpretation['weakest']['bucket']}"
            )
        if confidence_interpretation["most_overconfident"]:
            evidence.append(
                "Largest diagnostic overconfidence gap: "
                f"{confidence_interpretation['most_overconfident']['bucket']}"
            )
        if confidence_interpretation["most_underconfident"]:
            evidence.append(
                "Largest diagnostic underconfidence gap: "
                f"{confidence_interpretation['most_underconfident']['bucket']}"
            )
        if grade_interpretation["strongest"]:
            evidence.append(
                "Strongest reliable grade by Net R: "
                f"{grade_interpretation['strongest']['grade']}"
            )
        if grade_interpretation["weakest"]:
            evidence.append(
                "Weakest reliable grade by Net R: "
                f"{grade_interpretation['weakest']['grade']}"
            )

        if not evidence:
            evidence.append("Not enough reliable historical evidence for bucket conclusions.")

        return {
            "scope": report["scope"],
            "ai_rank_score": report["ai_rank_score"],
            "confidence": report["confidence"],
            "grade": report["grade"],
            "interpretation": {
                "ai_rank_score": ai_interpretation,
                "confidence": confidence_interpretation,
                "grade": grade_interpretation,
            },
            "evidence": evidence,
            "warnings": warnings,
            "ready_for_tuning": summary["ready_for_tuning"],
            "guardrail": "REPORT_ONLY: no AI weights, confidence formula, thresholds, grade rules, or scanner entry rules are changed.",
        }

    def render_text(self):
        """Render a concise human-readable report without changing state."""
        result = self.compute()
        scope = result["scope"]
        lines = [
            "Phase 2D-B2 Calibration Report",
            "================================",
            f"Signals: {scope['total_signals']} | Resolved: {scope['resolved_signals']} | Expired: {scope['expired_signals']}",
            f"AI samples: {scope['ai_calibration_samples']} | Confidence samples: {scope['confidence_calibration_samples']} | Min sample: {scope['min_sample']}",
            "",
            "AI Rank Score",
        ]
        for bucket, data in result["ai_rank_score"].items():
            if data:
                lines.append(
                    f"  {bucket}: n={data['n']} WR={data['win_rate_pct']}% AvgR={data['avg_r']} NetR={data['net_r']} reliable={data['reliable']}"
                )
            else:
                lines.append(f"  {bucket}: no resolved samples")

        lines.append("")
        lines.append("Confidence")
        for bucket, data in result["confidence"].items():
            if data:
                lines.append(
                    f"  {bucket}: n={data['n']} predicted={data['mean_predicted_pct']}% WR={data['win_rate_pct']}% error={data['calibration_error_pct']}pp reliable={data['reliable']}"
                )
            else:
                lines.append(f"  {bucket}: no resolved samples")

        lines.append("")
        lines.append("Grade")
        for grade, data in result["grade"].items():
            lines.append(
                f"  {grade}: n={data['n']} WR={data['win_rate_pct']}% AvgR={data['avg_r']} NetR={data['net_r']} reliable={data['reliable']}"
            )

        lines.append("")
        lines.append("Evidence")
        lines.extend(f"  - {item}" for item in result["evidence"])
        if result["warnings"]:
            lines.append("")
            lines.append("Warnings")
            lines.extend(f"  - {item}" for item in result["warnings"])

        lines.append("")
        lines.append(f"Ready for tuning: {result['ready_for_tuning']}")
        lines.append(result["guardrail"])
        return "\n".join(lines)


if __name__ == "__main__":
    print(CalibrationReport().render_text())
