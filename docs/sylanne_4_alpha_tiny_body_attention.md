# Sylanne 4.0 alpha 微型身体注意力层

Sylanne 已经接入外部 LLM。LLM 负责语言，tiny body attention 负责身体流通。这个层不是语言模型，也不替代 LLM；它是 Sylanne 的神经网络，把事件、器官、需要、记忆和边界拆成小 token，让它们在一次很短的 attention pass 里互相牵动。

## 目标

4.0 alpha 的旧向量层已经能把事件映射到 body delta，但它更像固定反射。微型身体注意力层要补上“局部碎片之间的互相看见”：安全信号会同时牵动 bloodflow、temperature、immunity；伤害信号会先碰到 wound 和 nerve，再让 repair need 升高；沉默不会直接变成一句话，而是先积累 contact need、readiness 和 mortality load。

它运行在 1C 1G 这种低端容器上，所以设计边界必须很硬：token_count <= 32，hidden_dim <= 32，layers = 1，heads <= 2。复杂度写成 O(T^2 d)，在这里也只是几十个 token 乘几十维，不是 LLM 级别的推理。

## 表示

每个身体片段是一个 token：

```text
organ.pulse
organ.bloodflow
organ.nerve
organ.muscle
organ.temperature
organ.wound
law.immunity
organ.mortality
need.contact
need.quiet
need.repair
need.expression
event.safe
event.hurt
event.boundary
event.repair
event.idle
event.has_text
```

每个 token 只携带 1 到 4 个 float。它们不是词向量，不存自然语言，不参与生成文本。文本在进入这里之前已经被压成事件轴。

## 推导

设身体 token 序列为

```text
B_t = {b_1, b_2, ..., b_n}, n <= 32
```

事件 token 序列为

```text
E_t = {e_1, e_2, ..., e_m}
```

合并后得到

```text
Z_t = B_t ∪ E_t
```

注意力层的形式仍然是标准结构：

```text
A = softmax(QK^T / sqrt(d))
H = A V
```

但这里的 Q、K、V 不是大语言模型里的语义空间，而是手工约束的身体通路空间。实现上保持确定性投影，让 `event.safe` 主要看向 bloodflow、temperature、immunity、muscle；让 `event.hurt` 主要看向 wound、nerve、immunity、mortality。

之后把 H 投影回状态增量：

```text
Delta x_t = P(H)
x_{t+1} = clamp(x_t + Delta x_t, 0, 1)
```

这里的 P 必须小，并且有硬限幅。当前实现把单轴 delta 限制在 [-0.08, 0.08]，避免一次事件把身体打穿。

## 和 LLM 的关系

LLM 在外层：理解一句话、生成一句话、把复杂语义压成事件。tiny body attention 在内层：决定这些事件在 Sylanne 身体里怎么流动。

```text
用户输入
→ LLM/规则提取事件
→ event token
→ tiny body attention
→ body delta
→ need / impulse
→ symbolic guard
→ host payload
→ LLM 表达
```

这就是 Sylanne 的分工：LLM 是语言皮层，tiny body attention 是神经网络，symbolic guard 是免疫和边界系统。

## 为什么 guard 不能交给 attention

Attention 可以产生冲动，但不能拥有最终行动权。主动靠近、修复、等待、退后，都必须经过 symbolic guard。原因很简单：边界不是概率问题。用户没 opt-in、cooldown 没结束、budget 不够、风险过高时，attention 只能表达“想”，不能直接“做”。

## 低端容器策略

1C 1G 的安全运行方式：

```text
token_count <= 32
hidden_dim <= 32
layers = 1
heads <= 2
recent_memory_tokens <= 4
只在消息事件或低频主动检查时运行
```

不要后台高频 tick，不要把长期记忆全塞进 attention，不要假设有显卡，不要让它变成第二个语言模型。真正昂贵的部分仍然是外部 LLM、网络等待、日志和持久化；这个层只做几十个浮点数的身体流通。

## 工程含义

这个设计把“数据打碎到不能再碎”的想法落到核心里。碎片不是散乱字段，而是会互相注意的身体片段。Sylanne 的连续性不再只靠一组公式维持，而是靠一个小型、可解释、可限幅的神经流通层维持。

一句话：tiny body attention 让 Sylanne 有神经网络，但不让神经网络夺走她的边界。
