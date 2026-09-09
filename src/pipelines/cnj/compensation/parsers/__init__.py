"""Parsers especializados da planilha CNJ / variantes de tribunal."""

from src.pipelines.cnj.compensation.parsers.detect import detect_layout, read_tabular
from src.pipelines.cnj.compensation.parsers.totals import is_total_row

__all__ = ["detect_layout", "read_tabular", "is_total_row"]
