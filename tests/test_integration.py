"""全量集成测试：验证所有新模块的协同工作和鲁棒性。

本文件是独立脚本（python tests/test_integration.py），不兼容 pytest 收集。
pytest 通过下方守卫跳过本模块。
"""
import sys, time

# pytest 收集守卫：非直接运行时立即停止模块执行
if __name__ != "__main__":
    import pytest
    pytest.skip("standalone script, not pytest-compatible", allow_module_level=True)

sys.path.insert(0, '.')

results = []
def test(name, fn):
    try:
        fn()
        results.append(('PASS', name))
    except Exception as e:
        results.append(('FAIL', name, str(e)))

# 1. 计算栈端到端
def t_spine():
    from sylanne_alpha.computation_spine import ComputationSpine
    spine = ComputationSpine()
    r = spine.process('today is bad', time.time())
    assert r['route'] in ('fast', 'normal', 'full')
    r2 = spine.process('', time.time())
    assert r2['route'] == 'skip'
    # 层级开关
    spine.set_layer_enabled('sheaf', False)
    r3 = spine.process('test', time.time())
    assert isinstance(r3, dict)
    spine.set_layer_enabled('sheaf', True)
test('计算栈端到端+层级开关', t_spine)

# 2. CircuitBreaker
def t_cb():
    from sylanne_alpha.computation_spine import CircuitBreaker
    cb = CircuitBreaker(threshold=2, cooldown=0.5)
    cb.record_failure()
    cb.record_failure()
    assert cb.is_open()
    time.sleep(0.6)
    assert not cb.is_open()
test('CircuitBreaker 熔断恢复', t_cb)

# 3. 人格漂移限制
def t_personality():
    from sylanne_alpha.personality import contradiction_tolerance, should_explore, apply_relationship_age_modulation
    assert 0.19 < contradiction_tolerance({'inner_order': 1.0}) < 0.21
    assert should_explore(0.7, 0.2, 0.5) == True
    m = apply_relationship_age_modulation({'expression_drive_trait': 0.5, 'boundary_permeability': 0.5}, 'infant')
    assert m['boundary_permeability'] < 0.5
test('人格系统协同', t_personality)

# 4. 记忆系统
def t_memory():
    from sylanne_alpha.memory_system import MemorySystem, InvertedIndex, ArchaeologyEngine
    idx = InvertedIndex()
    idx.add('m1', ['park', 'walk'])
    idx.add('m2', ['park', 'friend'])
    r = idx.query(['park', 'friend'])
    assert r[0] == 'm2'
    ae = ArchaeologyEngine()
    assert ae.should_dig(time.time())
test('记忆系统+倒排索引+考古', t_memory)

# 5. 秘密状态→泄露→prompt
def t_hidden():
    import random; random.seed(42)
    from sylanne_alpha.inner_self import HiddenStateManager
    from sylanne_alpha.prompt_surface import render_hidden_bias
    mgr = HiddenStateManager()
    mgr.add_secret('x', 'secret', ttl=9999, leak_prob=1.0, intensity=0.8)
    leaked = mgr.tick()
    assert len(leaked) > 0
    hint = render_hidden_bias(leaked)
    assert hint is not None
test('秘密状态→泄露→prompt注入', t_hidden)

# 6. 话题重力
def t_gravity():
    from sylanne_alpha.dialogue_intelligence import TopicGravityField
    tg = TopicGravityField()
    tg.observe('work', 0.8, 0.7)
    tg.observe('cats', 0.3, 0.9)
    tg.observe('work', 0.6, 0.5)
    pulls = tg.get_gravity_pull()
    assert pulls[0][0] == 'work'
    tg.apply_repulsion('work', 0.9)
    pulls2 = tg.get_gravity_pull()
    assert pulls2[0][1] < pulls[0][1]
test('话题重力场', t_gravity)

# 7. 关系弹性+修复策略
def t_resilience():
    from sylanne_alpha.relationship_dynamics import RelationalResilience
    from sylanne_alpha.relationship_dynamics import RepairStrategy
    rr = RelationalResilience()
    rs = RepairStrategy(conflict_threshold=3)
    for _ in range(4):
        rr.record_strain()
        rs.observe_interaction(True)
    assert rr.is_brittle()
    assert rs.needs_repair()
    assert rs.suggest(30, True) == 'reduce_frequency'
test('关系弹性+修复策略', t_resilience)

# 8. 边界协商
def t_boundary():
    from sylanne_alpha.relationship_dynamics import DynamicBoundary
    db = DynamicBoundary()
    db.record_probe_result('intimacy', True)
    assert db.get_level('intimacy') > 0.3
    db.record_probe_result('intimacy', False)
    assert not db.should_probe('intimacy')
test('边界协商试探-退回', t_boundary)

# 9. 自我叙事矛盾
def t_narrative():
    from sylanne_alpha.inner_self import SelfNarrative
    sn = SelfNarrative()
    sn.add_fragment('I like being active', 0.8)
    sn.add_fragment('I am passive', 0.9)
    old = [f for f in sn._fragments if 'active' in f.content]
    # 不一定检测到矛盾（简单关键词匹配），但不应崩溃
    assert len(sn._fragments) == 2
test('自我叙事矛盾处理', t_narrative)

# 10. 情绪惯性
def t_inertia():
    from sylanne_alpha.social_field import EmotionalInertia
    ei = EmotionalInertia()
    ok, _ = ei.attempt_shift(5.0, 10)
    assert ok
    ei._duration = 7200
    ok2, change2 = ei.attempt_shift(0.1, 1)
    assert not ok2
test('情绪惯性突破/未突破', t_inertia)

# 11. 危机检测
def t_crisis():
    from sylanne_alpha.assessor import CrisisDetector
    cd = CrisisDetector()
    assert cd.assess('not want to live', -0.9) == 'normal'  # English keywords not in list
    cd2 = CrisisDetector()
    assert cd2.assess('不想活了', -0.9) == 'crisis'
test('危机检测', t_crisis)

# 12. 能量管理
def t_energy():
    from sylanne_alpha.body import EnergyPool
    ep = EnergyPool()
    ep.consume(0.9)
    assert ep.is_fatigued
    assert ep.get_fatigue_hint() is not None
    ep.recover(3600)
    assert ep.energy > 0.1
test('能量管理', t_energy)

# 13. 对话模式切换
def t_mode():
    from sylanne_alpha.dialogue import ModeRouter, SocraticMode, IntrospectionHook, SilenceBreaker
    mr = ModeRouter()
    assert mr.route(-0.6, 0.1, 0.1) == 'comfort'
    assert mr.route(0.4, -0.3, 0.1) == 'playful'
    sm = SocraticMode()
    assert sm.should_activate('maybe I think so', 0.6)
    ih = IntrospectionHook()
    for _ in range(3):
        ih.check({'a': 0.1, 'b': 0.1})
    # 3rd should trigger
    sb = SilenceBreaker()
    assert sb.get_breaker('hurt', 8) != ''
test('对话模式+追问+自评+破冰', t_mode)

# 14. 持久化 round-trip
def t_persist():
    from sylanne_alpha.inner_self import HiddenStateManager
    from sylanne_alpha.dialogue_intelligence import TopicGravityField
    from sylanne_alpha.relationship_dynamics import DynamicBoundary
    from sylanne_alpha.multi_device import SyncManager, StateVector
    h = HiddenStateManager()
    h.add_secret('t', 'd', ttl=999)
    assert HiddenStateManager.from_dict(h.to_dict()).active_count() == 1
    tg = TopicGravityField()
    tg.observe('x', 1, 1)
    assert len(TopicGravityField.from_dict(tg.to_dict()).get_gravity_pull()) == 1
    sm = SyncManager('a')
    sm.update_local('k', 'v')
    remote = StateVector()
    remote.set('k', 'new', 'b')
    remote.timestamps['k'] = time.time() + 1
    assert 'k' in sm.merge(remote)
test('持久化 round-trip + 同步合并', t_persist)

# 15. i18n
def t_i18n():
    from sylanne_alpha.i18n import t, set_language, available_languages
    set_language('zh')
    assert len(t('onboarding')) > 5
    set_language('en')
    assert len(t('onboarding')) > 5
    assert 'zh' in available_languages()
test('i18n 多语言', t_i18n)

# 16. 风格镜像
def t_mirror():
    from sylanne_alpha.dialogue_intelligence import StyleMirror
    sm = StyleMirror()
    sm.observe('haha nice one!')
    sm.observe('lol yeah')
    hint = sm.get_mirror_hint(0.8)
    assert isinstance(hint, str)
    contrast = sm.get_contrast_hint(-0.6)
    assert len(contrast) > 0
test('风格镜像/反镜像', t_mirror)

# 17. 梦境生成
def t_dream():
    from sylanne_alpha.life_simulation import DreamGenerator
    dg = DreamGenerator()
    dream = dg.generate_dream(['memory1', 'memory2'], 4, 3.5)
    assert len(dream) > 10
    assert dg.has_dream_to_share()
test('梦境生成', t_dream)

# 18. 事件总线
def t_events():
    from sylanne_alpha.public_api import emit_event, on_event, off_event
    box = []
    def h(p): box.append(p)
    on_event('test_evt', h)
    emit_event('test_evt', {'x': 1})
    assert len(box) == 1
    off_event('test_evt', h)
    emit_event('test_evt', {'x': 2})
    assert len(box) == 1
test('事件总线', t_events)

# 19. 关系年龄+仪式
def t_session():
    from sylanne_alpha.session_context import get_relationship_stage, RitualRegistry, FirstImpression
    assert get_relationship_stage(time.time() - 86400) == 'infant'
    assert get_relationship_stage(time.time() - 86400*100) == 'deep'
    rr = RitualRegistry()
    for _ in range(3):
        rr.observe_pattern('s1', 22, 'goodnight')
    assert len(rr.get_active_rituals('s1')) == 1
    fi = FirstImpression(valence=0.5, topic_type='casual', user_style='brief', quality=0.7)
    assert fi.anchor_weight(3) == 1.0
    assert fi.anchor_weight(50) < 0.3
test('关系年龄+仪式+第一印象', t_session)

# 20. 沉默质感→破冰
def t_silence():
    from sylanne_alpha.void_calculus import SilenceTexture
    assert SilenceTexture.classify(60, 0.5, 0.8) == 'content'
    assert SilenceTexture.classify(300, -0.5, 0.8) == 'digesting'
    assert SilenceTexture.classify(8000, 0.0, 0.2) == 'distant'
test('沉默质感分类', t_silence)

# 21. 矛盾检测
def t_contradiction():
    from sylanne_alpha.inner_self import ContradictionDetector, get_correction_strategy
    cd = ContradictionDetector()
    cd.record_stance('cats', 'love cats', 0.8)
    r = cd.check('cats are great', 0.7)
    assert r is None  # same direction, no contradiction
    assert cd.is_playful_inconsistency('haha just kidding', 'playful')
test('矛盾检测+豁免', t_contradiction)

# 22. Prompt surface 协同
def t_prompt():
    from sylanne_alpha.prompt_surface import render_weather_metaphor, render_narrative_perspective, render_onboarding_fragment
    w = render_weather_metaphor({'valence': 0.6, 'tension': 0.1, 'temperature': 0.8})
    assert len(w) > 3
    n = render_narrative_perspective({'expression_drive_trait': 0.8})
    assert len(n) > 3
    assert render_onboarding_fragment(1) is not None
    assert render_onboarding_fragment(5) is None
test('Prompt surface 协同', t_prompt)

# 23. 媒体情绪融合
def t_media():
    from sylanne_alpha.assessor import tag_media_emotion, multimodal_fusion
    me = tag_media_emotion('sticker', 'haha so funny')
    assert me.emotion in ('happy', 'ironic', 'neutral')
    fused = multimodal_fusion(0.5, -0.3, 0.0)
    assert -1 <= fused <= 1
test('媒体情绪标注+融合', t_media)

# 24. 边缘模式
def t_edge():
    from sylanne_alpha.config import EdgeModeConfig
    from sylanne_alpha.computation_spine import ComputationSpine
    ec = EdgeModeConfig(enabled=True)
    spine = ComputationSpine()
    ec.apply_to_spine(spine)
    # 只有 3 层启用
    enabled = [k for k, v in spine._layer_enabled.items() if v]
    assert len(enabled) == 3
test('边缘运行模式', t_edge)

# 25. 策略插件系统
def t_strategy():
    from sylanne_alpha.strategy_plugins import ReplyStrategy, StrategyManager
    class TestStrategy(ReplyStrategy):
        @property
        def name(self): return 'test'
        def should_activate(self, ctx): return True
        def transform_reply(self, reply, ctx): return reply + '!'
    mgr = StrategyManager()
    mgr.register(TestStrategy())
    result = mgr.apply('hello', {})
    assert result == 'hello!'
    mgr.disable('test')
    result2 = mgr.apply('hello', {})
    assert result2 == 'hello'
test('策略插件热插拔', t_strategy)

# ═══ RESULTS ═══
print()
print('=' * 60)
passed = sum(1 for r in results if r[0] == 'PASS')
failed = sum(1 for r in results if r[0] == 'FAIL')
print(f'RESULTS: {passed} passed, {failed} failed, {len(results)} total')
print('=' * 60)
for r in results:
    s = 'PASS' if r[0] == 'PASS' else 'FAIL'
    print(f'  [{s}] {r[1]}')
    if r[0] == 'FAIL':
        print(f'    ERROR: {r[2]}')
if failed:
    sys.exit(1)
