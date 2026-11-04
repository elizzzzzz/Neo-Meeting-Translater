"""Scoring must use source revisions and stay outside the live socket callback."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("evaluate_streaming", Path(__file__).parents[1] / "scripts/evaluate_streaming.py")
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


def test_latency_uses_source_revision_and_final_stable_match():
    text = "这是用于测试的完整中文会议发言"
    def caption(at, source, **extra):
        return dict(type="caption", segment_id="one", wall_ms=at, original_text=source, **extra)
    timeline = [caption(1400, text), caption(1500, text[:-1] + "错"),
                caption(1600, text, translation_source_text=text, translation_complete=False),
                caption(2100, text, translation_source_text=text, translation_complete=True)]
    result = evaluation.score_timeline(timeline, [dict(start=0, end=1, text=text)])
    assert result["latencies"] == {0: 400}
    assert result["stable_lines"] == {0: 600}
    assert list(result["translation_first"].values()) == [200]
    assert result["translation_extra"] == [700]


def test_character_error_counts_keep_insertions_and_deletions():
    assert evaluation.character_errors("会议发言", "会议发言啊")["insertions"] == 1
    assert evaluation.character_errors("会议发言", "会议")["deletions"] == 2
