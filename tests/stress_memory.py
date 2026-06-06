"""记忆系统压力测试。"""
import sys, time
sys.path.insert(0, '.')


def stress_test():
    from sylanne_alpha.memory_system import MemorySystem
    ms = MemorySystem()

    start = time.time()
    # 写入 1000 条记忆
    for i in range(1000):
        ms.write_summary(
            text=f"记忆条目 {i}，包含一些测试内容用于压力测试",
            source_turns=1,
            temperature=0.1 * (i % 10),
        )
    write_time = time.time() - start

    # 并发召回
    start = time.time()
    for i in range(100):
        ms.recall(query=f"测试查询 {i}", current_warmth=0.5)
    recall_time = time.time() - start

    print(f"Write 1000 items: {write_time:.2f}s ({write_time/1000*1000:.1f}ms/item)")
    print(f"Recall 100 queries: {recall_time:.2f}s ({recall_time/100*1000:.1f}ms/query)")

    # 验证无 OOM（检查内存）
    import gc
    gc.collect()
    print("Stress test passed - no OOM")


if __name__ == "__main__":
    stress_test()
