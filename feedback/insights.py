"""Local, descriptive keyword counts. No OCR, external AI or attainment claims."""
import logging
import re
from collections import Counter, defaultdict
from functools import lru_cache
import jieba

STOP = set('老师 同学 学生 这个 那个 什么 为什么 怎么 如何 请问 谢谢 问题 知识点 不懂 不会 不明白 理解 感觉 可以 需要 不能 直接 时候 进行 一个 一下 还是 有点 这里 那里 请帮 帮忙 解释 计算 公式 求解 求出'.split())
DOMAIN = '极限 连续性 可导性 导数 求导 偏导数 方向导数 全微分 定积分 不定积分 二重积分 三重积分 换元积分 分部积分 隐函数 泰勒公式 无穷级数 收敛性 条件概率 贝叶斯 正态分布 数学期望 方差 样本均值 标准差 协方差 置信区间 假设检验 特征值 特征向量 行列式 矩阵 线性无关'.split()
ALIASES = {'求导':'导数', '不定积分':'不定积分', '期望':'数学期望', '可导':'可导性', '连续':'连续性', '收敛':'收敛性'}


@lru_cache(maxsize=1)
def tokenizer():
    jieba.setLogLevel(logging.WARNING)
    instance = jieba.Tokenizer()
    for word in DOMAIN:
        instance.add_word(word, freq=10000)
    return instance


def terms(text):
    text = re.sub(r'\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]|\$\$[\s\S]*?\$\$|\$[^$\n]*\$', ' ', text)
    return {ALIASES.get(word, word) for word in tokenizer().cut(text.lower(), HMM=False)
            if word not in STOP and re.fullmatch(r'[\u3400-\u9fff]{2,16}|[a-z]{3,16}', word)}


def keyword_insights(records):
    questions = [r for r in records if r.status in ('yellow', 'red')]
    counts, examples, modules = defaultdict(set), defaultdict(list), defaultdict(set)
    for question in questions:
        student = question.user_id or str(question.participant)
        module = getattr(question,'block_title','') or (str(question.block) if question.block_id else '未指定模块')
        modules[module].add(student)
        for term in terms(question.note):
            counts[term].add(student)
            if len(examples[term]) < 3 and question.note[:160] not in examples[term]:
                examples[term].append(question.note[:160])
    students = len({r.user_id or str(r.participant) for r in questions})
    return {'students': students, 'questions': len(questions), 'text_questions': sum(bool(r.note.strip()) for r in questions),
            'terms': [{'term': term, 'count': len(users), 'percent': round(100*len(users)/students) if students else 0,
                       'examples': examples[term]} for term, users in sorted(counts.items(), key=lambda item:(-len(item[1]),item[0]))[:20]],
            'modules': [{'title': title, 'count': len(users)} for title,users in sorted(modules.items(),key=lambda item:(-len(item[1]),item[0]))]}


def student_sort_key(value):
    value = (value or '').strip()
    return (not bool(value), tuple((0, int(p)) if p.isdigit() else (1, p.casefold())
                                  for p in re.split(r'(\d+)', value) if p), value.casefold())
