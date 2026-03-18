"""按 path_id 从 launch_path / capture_path CSV 加载点行。"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Dict, List


def loadSegmentCsvByPathId(csv_path: Path) -> Dict[str, List[dict]]:
    """读取点表 CSV，按 path_id 分组；每组内按 point_index 排序。"""
    if not csv_path.is_file():
        return {}
    by_pid: dict[str, List[dict]] = defaultdict(list)
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            pid = (row.get("path_id") or "").strip()
            if not pid:
                continue
            by_pid[pid].append(row)
    for pid in by_pid:
        by_pid[pid].sort(key=lambda r: int((r.get("point_index") or "0").strip() or 0))
    return dict(by_pid)
