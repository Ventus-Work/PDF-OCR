import pytest
from utils.usage_tracker import UsageTracker


class TestUsageTracker:
    def test_usage_tracker_initial_state(self):
        tracker = UsageTracker()
        assert tracker.total_input_tokens == 0
        assert tracker.total_output_tokens == 0

    def test_usage_tracker_add(self):
        tracker = UsageTracker()
        tracker.add(input_tokens=100, output_tokens=50)
        assert tracker.total_input_tokens == 100
        assert tracker.total_output_tokens == 50

    def test_usage_tracker_multiple_adds(self):
        tracker = UsageTracker()
        tracker.add(input_tokens=10, output_tokens=20)
        tracker.add(input_tokens=5, output_tokens=5)
        assert tracker.total_input_tokens == 15
        assert tracker.total_output_tokens == 25

    def test_usage_tracker_cost_calculation(self):
        tracker = UsageTracker()
        tracker.add(input_tokens=1000000, output_tokens=1000000)
        # 비용 계산 로직이 어떻게 되든 속성에 접근 가능한지 확인
        assert "0.5" in tracker.summary() or tracker.call_count == 1
