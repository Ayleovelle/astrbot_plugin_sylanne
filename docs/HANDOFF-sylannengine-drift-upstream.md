# SylannEngine 远端改动清单 — 把"对话质量自我进化漂移"做进 SDK canonical

> 目标仓库:**github.com/Ayleovelle/SylannEngine**(branch: main)——**不是** Sylanne-next
> 背景:Sylanne-next 当年为了 CP8-P4「越聊越校准」自我进化,把一条漂移接线手搓焊进了 vendored SDK(`feedback_quality` 方法 + `dialogue_quality_*` 两条 DRIFT_SIGNALS)。它焊错了位置(应在 SDK canonical 或 agent 层),导致 vendored 与远端 main 分叉、整树同步时丢失。
> 本清单:把其中**属于 SDK 的动力学部分**用 canonical 正道补进远端 main,退役 `feedback_quality` 后门。做完远端发版,Sylanne-next 直接整树同步 vendored 即可。

---

## 一、判断依据(为什么这部分该进 SDK,那部分不该)

| 组成 | 性质 | 归属 | 处置 |
|---|---|---|---|
| `self_score(text, response)` 三维质量启发式 | 应用层判断("什么叫好回复") | **agent 层(Sylanne-next)** | 留在 `sylanne_alpha/dialogue.py`,不进 SDK |
| `dialogue_quality_high/low → trait` 映射 | 漂移动力学规则(与 expression_fired 同性质) | **SDK** | 进远端 `DRIFT_SIGNALS` |
| `ResonanceSpine` 漂移线接入 | 引擎自身机制(ComputationSpine 已有,ResonanceSpine 留空) | **SDK** | 远端补 canonical 接线 |
| `feedback_quality()` 方法 | 绕开 observe/tick/snapshot 的"第四写动词"后门 | **退役** | 不进 SDK;agent 改走标准通道 |

核心原则:**质量判断(吃文本)留 agent;漂移动力学(吃信号→推 trait)进 SDK;不开后门,走 `process()` 自动漂移的 canonical 正道。** SDK 即 SylannEngine 本体(非通用库),故 `dialogue_quality` 这类 Sylanne 概念进 SDK 不算污染。

---

## 二、远端 main 现状(已核实,clone main 实测)

- `ResonanceSpine`(运行时默认 spine,torch 在场时加载)的 embodiment 漂移**基建字段全有**:
  `_embodiment_traits` / `_signal_extractor`(DriftSignalExtractor) / `_oscillation_detector` / `_drift_attribution` / `_drift_tick` / `_last_drift_time` / `_drift_min_interval` / `_last_embodiment_apply` / `_last_process_time` —— 全 ✓
- **但 `ResonanceSpine.process()` 从不调用漂移**:全文无 `_drift_embodiment` 方法、无 `compute_embodiment_drift(` 调用、无 `_signal_extractor.extract(` 调用。基建就绪、接线缺失。
- `ComputationSpine`(非默认)**已有** `_drift_embodiment` 且 `process()` 已调(范本)。
- `DRIFT_SIGNALS`(personality.py)有 `expression_fired`/`sustained_silence` 等,**无** `dialogue_quality_*`。
- `_REVERSE_LEGACY_MAP` 在 personality.py 定义且已 `__all__` 导出,ResonanceSpine 可导入。

结论:远端要做的是**纯接线**,基建无需新建。

---

## 三、远端 main 具体改动(3 处)

### 改动 1 — `personality.py`:`DRIFT_SIGNALS` 加两条质量映射

在 `DRIFT_SIGNALS` 字典里,紧跟 `sustained_silence` 之后加入(与 vendored 当年焊的语义一致):

```python
    # 对话质量自评信号（CP8-P4 自我进化：self_score 三维质量 → 人格漂移）
    "dialogue_quality_high": [   # 回复质量高 → 强化表达欲 + 拉近关系
        ("expression_drive_trait", +0.25),
        ("relational_gravity", +0.15),
    ],
    "dialogue_quality_low": [("expression_drive_trait", -0.15)],  # 质量低 → 收敛表达欲
```

注:`DriftSignalExtractor.extract()` 当前从 `result` 的 `should_express`/`route`/`emotion` 派生信号,**不产 dialogue_quality_***(因为质量判断在 agent 层、SDK 拿不到文本)。所以这两个信号靠 agent 层经 result 注入(见改动 3 + 四节)。

### 改动 2 — `resonance_integration.py`:`ResonanceSpine` 补 `_drift_embodiment` 方法

照抄 `ComputationSpine._drift_embodiment`(canonical 范本),贴进 `ResonanceSpine`。需确保:
- `from .personality import compute_embodiment_drift, _REVERSE_LEGACY_MAP`(若未导入)
- 方法体与 ComputationSpine 版逐字一致(速率限制 `_drift_min_interval`、`extract`、`compute_embodiment_drift`、变化 >0.01 才 `apply_personality` 重应用)
- 所有依赖字段 ResonanceSpine 已具备(已核实),无需新建

### 改动 3 — `resonance_integration.py`:`ResonanceSpine.process()` 末尾调一次

在 `process()` 的 `return result`(当前约 509 行)**之前**加:

```python
        self._drift_embodiment(result)
        return result
```

与 ComputationSpine.process 同位语义(它在 return 前调 `self._drift_embodiment(result)`)。

---

## 四、配套:agent 层(Sylanne-next)如何喂质量信号(远端发版后做)

远端做完后,质量信号要进 `process()` 的 `result` 才能被 `DriftSignalExtractor` 提取。两条路二选一(**这条留待 Sylanne-next 侧拍板,不在远端清单内**):

- **(优先)扩展 `DriftSignalExtractor.extract`**:认 `result.get("dialogue_quality")` 字段 → 产 `dialogue_quality_high/low`。agent 层把 self_score 结果塞进喂给 tick 的 event/result。最对齐"自动漂移",彻底无后门。
- **(次选)agent 层自带映射**:不依赖 SDK 提取,agent 读 `comp._embodiment_traits` + import `compute_embodiment_drift` 自驱。但这又是半个后门,不推荐。

---

## 五、做完后 Sylanne-next 侧的收尾

1. 远端 SylannEngine main 发版(含改动 1-3)
2. Sylanne-next 整树同步 vendored ← 远端 main(本次已验证 52 文件同步机制可行)
3. 删除 agent 层对 `feedback_quality` 的调用:
   - `sylanne_alpha/agents/dialogue_agent.py:63-68`(v1 线,且 v1 已退役,可整段清)
   - `sylanne_alpha/v2core/body_port_v2.py:199-206`(改走改动 3 的标准通道:把 quality 塞 result,不再 `getattr(comp,"feedback_quality")`)
4. 更新 7 个失败测试:从"断言 `feedback_quality` 驱动漂移"改为"断言经 `process()` 自动漂移"
5. `self_score` 原样留 `sylanne_alpha/dialogue.py`,不动

---

## 六、收益

- vendored SDK 永远是远端 main 的**干净镜像**,未来 SDK 升级不再撞这条线(本次分叉的根因消除)
- 自我进化漂移走 canonical `process()` 自动通道,退役"第四写动词"后门
- 质量判断(应用层)与漂移动力学(引擎层)边界清晰
- 满足两条硬约束:**本仓库 SDK 不手改**(改在远端)+ **接口对齐换上就行**(漂移线补进 canonical 后,vendored 与远端零分叉)

---

## 附:本清单所有事实的核实出处(防幻觉)

- `ResonanceSpine` 字段齐全:clone main 实测 grep,7 字段全 ✓
- `process()` 不调漂移:`grep _drift_embodiment|compute_embodiment_drift|super().process` 于 resonance_integration.py 全空
- `feedback_quality` 全远端仓不存在:`grep -rn feedback_quality .` 空(仅 vendored 有)
- `ComputationSpine._drift_embodiment` 范本:computation_spine.py:977-1025,process 在 877 调
- `DRIFT_SIGNALS` 无 dialogue_quality:逐行对比 vendored-HEAD vs remote main,差异仅这两条
- `self_score` 纯文本启发式:dialogue.py:139,只吃 text/response 字符串,不碰引擎状态
- 运行时默认 spine = ResonanceSpine:实跑 `_DEFAULT_SPINE.__name__` 确认(torch 在场)
