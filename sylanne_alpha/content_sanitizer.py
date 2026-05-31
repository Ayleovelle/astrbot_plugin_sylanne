"""内容净化模块——为 LLM 摘要/评估请求过滤敏感内容。

问题背景：
  当对话包含 R18/NSFW 内容时，LLM 提供商的安全过滤器会拒绝摘要和评估请求，
  导致整个记忆管线静默失败（返回空字符串）。本模块在发送给 LLM 之前将显式内容
  抽象为情感/行为标签，保留语义信息的同时绕过安全过滤。

设计原则：
  - 快速：assessment 路径每条消息都跑，必须低延迟
  - 不过度净化：情感词（爱、想你、心疼）不应被过滤
  - 保留：情感上下文、关系动态、对话流、事实信息、人名
  - 剥离：图形化身体描述、显式性内容、暴力细节
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# 关键词模式（编译后缓存）
# ---------------------------------------------------------------------------

# 显式身体部位词汇
_BODY_PARTS_ZH = (
    r"乳房|乳头|奶头|胸部|胸脯|乳沟|奶子|咪咪"
    r"|阴茎|阳具|肉棒|鸡巴|龟头|睾丸|蛋蛋"
    r"|阴道|阴唇|阴蒂|小穴|花穴|蜜穴|肉穴|骚穴|淫穴"
    r"|屁股|臀部|肛门|菊花|后穴"
    r"|精液|淫液|爱液|蜜液|体液"
)

# 显式性行为词汇
_SEXUAL_ACTS_ZH = (
    r"插入|抽插|抽送|顶弄|贯穿|深入|捅"
    r"|口交|吞吐|含住|舔弄|舔舐|吮吸"
    r"|手淫|自慰|撸动|套弄|揉捏|揉搓"
    r"|高潮|射精|潮吹|绝顶|泄出|射了|射在"
    r"|做爱|性交|交合|交媾|云雨|颠鸾倒凤"
    r"|骑乘|后入|正常位|侧入|深喉"
    r"|捆绑|调教|鞭打|滴蜡|窒息"
)

# 显式修饰词/状态描述
_EXPLICIT_ADJ_ZH = (
    r"淫荡|淫靡|淫乱|骚浪|浪叫|呻吟|娇喘|媚叫"
    r"|湿透|湿润|泥泞|黏腻|滑腻"
    r"|肿胀|充血|挺立|硬挺|勃起"
    r"|赤裸|全裸|裸体|一丝不挂"
    r"|情欲|肉欲|兽欲|发情|发骚"
)

# 英文显式词汇
_EXPLICIT_EN = (
    r"\b(?:fuck(?:ing|ed)?|cock|dick|pussy|cunt|tits|boobs"
    r"|cum(?:ming)?|orgasm|penetrat(?:e|ion)|thrust(?:ing)?"
    r"|moan(?:ing|ed)?|naked|nude|erect(?:ion)?|masturbat"
    r"|blowjob|handjob|anal|vaginal|genital|nipple"
    r"|bondage|spank(?:ing)?|dominat)"
)

# 暴力/血腥细节
_VIOLENCE_ZH = (
    r"鲜血喷涌|血肉模糊|内脏|肠子流出|脑浆|断肢"
    r"|肢解|开膛|剖腹|割喉|挖眼|剥皮"
)

# 合并为主过滤模式
_EXPLICIT_PATTERN = re.compile(
    f"(?:{_BODY_PARTS_ZH}|{_SEXUAL_ACTS_ZH}|{_EXPLICIT_ADJ_ZH}"
    f"|{_EXPLICIT_EN}|{_VIOLENCE_ZH})",
    re.IGNORECASE,
)

# 匹配包含显式内容的完整句段（中文句号/感叹号/问号/逗号/换行分隔）
_SENTENCE_SPLIT = re.compile(r"[。！？，,\n]+")

# 用于 assessment 的轻量检测——只要句子含显式词就整句替换
_SENSITIVE_SENTENCE = re.compile(
    f"[^。！？\\n]*(?:{_BODY_PARTS_ZH}|{_SEXUAL_ACTS_ZH}|{_EXPLICIT_ADJ_ZH}"
    f"|{_EXPLICIT_EN}|{_VIOLENCE_ZH})[^。！？\\n]*",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# 替换标签映射
# ---------------------------------------------------------------------------

_TAG_INTIMATE = "[亲密互动]"
_TAG_BODY = "[身体接触]"
_TAG_EMOTION = "[情感表达]"
_TAG_ADULT = "[成人内容]"
_TAG_VIOLENCE = "[暴力描写]"
_TAG_SENSITIVE = "[敏感内容]"

_VIOLENCE_PATTERN = re.compile(f"(?:{_VIOLENCE_ZH})", re.IGNORECASE)
_SEXUAL_PATTERN = re.compile(
    f"(?:{_SEXUAL_ACTS_ZH}|{_EXPLICIT_EN})", re.IGNORECASE
)
_BODY_PATTERN = re.compile(f"(?:{_BODY_PARTS_ZH})", re.IGNORECASE)
_ADJ_PATTERN = re.compile(f"(?:{_EXPLICIT_ADJ_ZH})", re.IGNORECASE)

# ---------------------------------------------------------------------------
# LLM 拒绝响应检测
# ---------------------------------------------------------------------------

CONTENT_FILTER_REFUSAL_PATTERNS: list[str] = [
    "我无法",
    "我不能",
    "无法为你",
    "不能为你",
    "违反",
    "安全政策",
    "内容政策",
    "不适当",
    "不当内容",
    "敏感内容",
    "I cannot",
    "I can't",
    "I'm unable",
    "content policy",
    "safety policy",
    "inappropriate",
    "violates",
    "against my",
    "not appropriate",
    "harmful content",
    "explicit content",
    "I'm not able to",
    "as an AI",
    "作为AI",
    "作为人工智能",
]

_REFUSAL_PATTERN = re.compile(
    "|".join(re.escape(p) for p in CONTENT_FILTER_REFUSAL_PATTERNS),
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------


def _classify_sentence(sentence: str) -> str:
    """对单个句段分类，返回替换标签或原文。"""
    if not _EXPLICIT_PATTERN.search(sentence):
        return sentence
    if _VIOLENCE_PATTERN.search(sentence):
        return _TAG_VIOLENCE
    if _SEXUAL_PATTERN.search(sentence):
        return _TAG_ADULT
    if _BODY_PATTERN.search(sentence):
        return _TAG_BODY
    if _ADJ_PATTERN.search(sentence):
        return _TAG_INTIMATE
    return _TAG_SENSITIVE


def sanitize_for_summary(text: str) -> str:
    """净化文本用于 LLM 摘要请求。

    将显式内容替换为抽象情感/行为标签，保留情感上下文和对话结构。
    """
    if not text:
        return text
    # 快速路径：无显式内容则直接返回
    if not _EXPLICIT_PATTERN.search(text):
        return text

    segments = _SENTENCE_SPLIT.split(text)
    result_parts: list[str] = []
    prev_was_tag = False

    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        classified = _classify_sentence(seg)
        # 连续相同标签去重
        if classified.startswith("[") and classified == (result_parts[-1] if result_parts else ""):
            continue
        # 连续不同标签合并为通用标签
        if classified.startswith("[") and prev_was_tag:
            if result_parts and result_parts[-1] != classified:
                result_parts[-1] = _TAG_ADULT
            continue
        result_parts.append(classified)
        prev_was_tag = classified.startswith("[")

    return "。".join(result_parts)


def sanitize_for_assessment(text: str) -> str:
    """轻量净化用于 assessment 路径。

    assessment 只需要情感极性/唤醒度/意图，因此用更粗粒度的替换。
    保留情感指示词，仅将显式段落替换为 [敏感内容]。
    """
    if not text:
        return text
    if not _EXPLICIT_PATTERN.search(text):
        return text
    # 整句替换，不做细分类
    result = _SENSITIVE_SENTENCE.sub(_TAG_SENSITIVE, text)
    # 去重连续标签
    result = re.sub(rf"(?:{re.escape(_TAG_SENSITIVE)}[，,\s]*)+", _TAG_SENSITIVE, result)
    return result


def wrap_system_prompt_for_analysis(base_prompt: str) -> str:
    """为分析任务包装系统提示词，降低安全过滤器误触发概率。

    在 base_prompt 前添加临床/分析框架声明，引导 LLM 以结构化分析模式处理内容。
    """
    framing = (
        "你是对话分析系统，正在执行结构化情感分析任务。"
        "以下内容仅用于提取情感维度和关键事实，不需要复述或评判原文内容。"
        "请以客观分析视角处理，直接输出结构化结果。\n\n"
    )
    return framing + base_prompt


def is_content_filter_refusal(response: str) -> bool:
    """检测 LLM 响应是否为安全过滤拒绝。

    用于区分「LLM 拒绝回答」和「LLM 调用失败/超时返回空」两种情况。
    短响应（<200字符）中命中拒绝模式即判定为拒绝。
    长响应中需要在前 100 字符内命中才算（避免正文中偶然包含关键词）。
    """
    if not response or not response.strip():
        return False
    text = response.strip()
    # 短响应：整体检测
    if len(text) < 200:
        return bool(_REFUSAL_PATTERN.search(text))
    # 长响应：仅检测开头
    return bool(_REFUSAL_PATTERN.search(text[:100]))
