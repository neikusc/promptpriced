"""Observed latency statistics, independent of token prices."""
import math
from statistics import mean, median
from .pricing import number


def timing_profile(samples):
    values = sorted(v for s in samples if (v := number(s.get('total_ms'))) is not None and v > 0)
    if not values:
        return None
    ttft = [v for s in samples if (total := number(s.get('total_ms'))) is not None
            and total > 0 and (v := number(s.get('ttft_ms'))) is not None and v <= total]
    return {'n': len(values), 'mean_ms': mean(values), 'median_ms': median(values),
            'min_ms': values[0], 'max_ms': values[-1],
            'p95_ms': values[math.ceil(.95 * len(values)) - 1],
            'mean_ttft_ms': mean(ttft) if ttft else None, 'ttft_n': len(ttft)}
