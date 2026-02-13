"""实时进度管理 — 将转录状态写入 status.json，供外部监控读取。"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import LOG_DIR

logger = logging.getLogger(__name__)

STATUS_FILE = LOG_DIR / "status.json"

# 转录阶段定义
STAGES = {
    "idle":       {"order": 0, "label": "⏸  空闲待机",           "progress": 0},
    "waiting":    {"order": 1, "label": "🚀 准备开始",           "progress": 5},
    "extract":    {"order": 2, "label": "🎵 提取音频 (1/4)",     "progress": 15},
    "detect":     {"order": 3, "label": "🌐 检测语言 (2/4)",     "progress": 25},
    "transcribe": {"order": 4, "label": "📝 转录中 (3/4)",       "progress": 40},
    "save":       {"order": 5, "label": "💾 保存文件 (4/4)",     "progress": 90},
    "done":       {"order": 6, "label": "✅ 转录完成",           "progress": 100},
    "failed":     {"order": 6, "label": "❌ 转录失败",           "progress": 100},
}


class ProgressManager:
    """
    管理转录进度状态，实时写入 JSON 文件。

    用法:
        pm = ProgressManager()
        pm.start("video.mp4", 120.5)
        pm.update("extract")
        pm.update("detect", detail="检测到中文")
        pm.update("transcribe", detail="音频 2.0 分钟", transcribe_percent=30)
        pm.finish(success=True, lang="zh", segments=42, speakers=2)
    """

    def __init__(self):
        self._start_time: Optional[float] = None
        self._filename: str = ""
        self._filesize_mb: float = 0
        self._duration_sec: float = 0
        self._current_stage: str = "idle"
        self._detail: str = ""
        self._transcribe_percent: int = 0
        self._error: str = ""
        self._history: list[dict] = []
        # 统计信息
        self._total_completed: int = 0
        self._total_failed: int = 0
        # 队列信息
        self._queue: list[dict] = []  # [{filename, filesize_mb, queued_at}, ...]
        # 初始化状态文件
        self._write_status()

    def _elapsed(self) -> float:
        """返回已用时间（秒）。"""
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    def _elapsed_str(self) -> str:
        """格式化已用时间。"""
        s = int(self._elapsed())
        if s < 60:
            return f"{s}s"
        m = s // 60
        s = s % 60
        return f"{m}m{s}s"

    def _compute_progress(self) -> int:
        """计算当前总进度百分比。"""
        stage_info = STAGES.get(self._current_stage, STAGES["idle"])
        base = stage_info["progress"]

        # 如果在转录阶段，细化进度 (40% ~ 90%)
        if self._current_stage == "transcribe" and self._transcribe_percent > 0:
            extra = int(self._transcribe_percent * 0.5)  # 50% 的空间分配给转录
            return min(base + extra, 90)

        return base

    def _write_status(self) -> None:
        """将当前状态写入 JSON 文件。"""
        stage_info = STAGES.get(self._current_stage, STAGES["idle"])

        status = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "state": self._current_stage,
            "state_label": stage_info["label"],
            "progress": self._compute_progress(),
            "filename": self._filename,
            "filesize_mb": round(self._filesize_mb, 1),
            "duration_sec": round(self._duration_sec, 1),
            "elapsed": self._elapsed_str(),
            "elapsed_sec": round(self._elapsed(), 1),
            "detail": self._detail,
            "transcribe_percent": self._transcribe_percent,
            "error": self._error,
            "stats": {
                "total_completed": self._total_completed,
                "total_failed": self._total_failed,
            },
            "queue": self._queue,
            "queue_position": 0,  # 仅占位，实际由消费者逻辑决定
            "history": self._history[-5:],  # 最近 5 条历史
        }

        try:
            STATUS_FILE.write_text(
                json.dumps(status, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"写入状态文件失败: {e}")

    def start(self, filename: str, filesize_mb: float, duration_sec: float = 0) -> None:
        """开始新的转录任务。"""
        self._start_time = time.time()
        self._filename = filename
        self._filesize_mb = filesize_mb
        self._duration_sec = duration_sec
        self._current_stage = "waiting"
        self._detail = ""
        self._transcribe_percent = 0
        self._error = ""
        self._write_status()
        logger.info(f"[进度] 开始: {filename}")

    def update(
        self,
        stage: str,
        detail: str = "",
        transcribe_percent: int = 0,
        duration_sec: float = 0,
    ) -> None:
        """更新转录阶段。"""
        self._current_stage = stage
        if detail:
            self._detail = detail
        if transcribe_percent > 0:
            self._transcribe_percent = transcribe_percent
        if duration_sec > 0:
            self._duration_sec = duration_sec
        self._write_status()

        stage_label = STAGES.get(stage, {}).get("label", stage)
        logger.info(f"[进度] {stage_label}" + (f" - {detail}" if detail else ""))

    def update_transcribe_progress(self, percent: int, detail: str = "") -> None:
        """细粒度更新转录进度百分比 (0-100)。"""
        self._transcribe_percent = min(percent, 100)
        if detail:
            self._detail = detail
        self._write_status()

    def finish(
        self,
        success: bool,
        lang: str = "",
        segments: int = 0,
        speakers: int = 0,
        output_file: str = "",
    ) -> None:
        """完成转录任务。"""
        elapsed = self._elapsed_str()

        if success:
            self._current_stage = "done"
            self._transcribe_percent = 100
            self._detail = f"语言: {lang} | 片段: {segments} | 说话人: {speakers}"
            self._total_completed += 1
            self._history.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "file": self._filename,
                "result": "✅",
                "lang": lang,
                "elapsed": elapsed,
            })
        else:
            self._current_stage = "failed"
            self._total_failed += 1
            self._history.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "file": self._filename,
                "result": "❌",
                "error": self._error[:50],
                "elapsed": elapsed,
            })

        self._write_status()
        logger.info(f"[进度] {'完成' if success else '失败'}: {self._filename} ({elapsed})")

    def set_error(self, error: str) -> None:
        """设置错误信息。"""
        self._error = error
        self._write_status()

    def reset_to_idle(self) -> None:
        """重置为空闲状态。"""
        self._current_stage = "idle"
        self._filename = ""
        self._filesize_mb = 0
        self._duration_sec = 0
        self._detail = ""
        self._transcribe_percent = 0
        self._error = ""
        self._start_time = None
        self._write_status()


    def add_to_queue(self, filename: str, filesize_mb: float) -> None:
        """添加文件到队列。"""
        self._queue.append({
            "filename": filename,
            "filesize_mb": round(filesize_mb, 1),
            "queued_at": datetime.now().strftime("%H:%M:%S"),
        })
        self._write_status()
        logger.info(f"[队列] 入队: {filename} (排队中: {len(self._queue)})")

    def remove_from_queue(self, filename: str) -> None:
        """从队列中移除文件（开始处理时调用）。"""
        self._queue = [item for item in self._queue if item["filename"] != filename]
        self._write_status()


# 全局单例
progress = ProgressManager()
