"""计算栈性能基准测试。"""
import sys, time
sys.path.insert(0, '.')

from sylanne_alpha.computation_spine import ComputationSpine

def bench():
    spine = ComputationSpine()
    text = "你好世界这是一段测试文本用于性能基准测试"

    # Warmup
    for _ in range(5):
        spine.process(text, 0.0)

    # Benchmark
    times = []
    for _ in range(100):
        start = time.perf_counter_ns()
        spine.process(text, 0.0)
        elapsed = (time.perf_counter_ns() - start) / 1_000_000  # ms
        times.append(elapsed)

    times.sort()
    p50 = times[49]
    p95 = times[94]
    p99 = times[98]
    print(f"Spine process() benchmark (100 iterations):")
    print(f"  p50: {p50:.2f}ms")
    print(f"  p95: {p95:.2f}ms")
    print(f"  p99: {p99:.2f}ms")
    print(f"  mean: {sum(times)/len(times):.2f}ms")

    # 回归阈值
    assert p95 < 50, f"p95 regression: {p95:.2f}ms > 50ms"

if __name__ == "__main__":
    bench()
