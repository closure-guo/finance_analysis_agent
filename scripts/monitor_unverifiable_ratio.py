#!/usr/bin/env python
"""定时监控 citation_unverifiable_ratio 突升（告警记录落 reports/monitoring/）。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # evals/ 未安装进 venv（packages.find where=src），需显式加根

from evals.unverifiable_monitor import main  # noqa: E402

if __name__ == "__main__":
    main()
