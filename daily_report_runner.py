"""
Daily Report Runner
Triggered by a separate GitHub Actions schedule (once per day).
"""

from reports.daily_report import DailyReport

if __name__ == "__main__":
    DailyReport().send()
