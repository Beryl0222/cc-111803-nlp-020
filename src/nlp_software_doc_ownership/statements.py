"""从自然语言指南与迁移说明中抽取陈述所指的接口、字段、版本与例外。

抽取只依赖标准库，规则均为可核对的正则与词表：每条陈述保留原句和来源，
后续审校结果可以追回到原文，而不是用推断替换原文。
"""
import re
from dataclasses import dataclass, field

from .text import normalize_text

# 中文叫法 -> 契约字段名
FIELD_GLOSSARY = {
    '作业编号': 'job_id',
    '编号': 'id',
    '票据编号': 'ticket',
    '票据': 'ticket',
    '状态': 'state',
    '游标': 'cursor',
}

EDITION_RE = re.compile(r'v\d+(?:\.\d+)*')
PATH_RE = re.compile(r'/[A-Za-z0-9_\-/]+')
FIELD_RE = re.compile(r'\$[A-Za-z_][A-Za-z0-9_]*')
DEFAULT_RE = re.compile(r'默认(?:值|为)?[:：]?\s*([A-Za-z0-9_\-]+)')
PREVIOUS_RE = re.compile(r'(上一步|上一个接口|前一个接口|前一步|下一步|后续)')
# “除旧网关外”一类例外：把限定范围与适用方式分开记录
EXCEPTION_RE = re.compile(r'除(?P<scope>[^，。；,;]{1,12}?)外')
SENTENCE_SPLIT_RE = re.compile(r'[。；;]')
MIGRATION_HINTS = ('迁移', '调整', '改为', '改成', '更名', '替换为', '不再返回')
DEPRECATION_HINTS = ('弃用', '停用', '下线', '不再支持')


@dataclass(frozen=True)
class Statement:
    """一句可核对的指南陈述。"""
    statement_id: str
    source: str
    revision: int
    sentence: str
    product: str | None
    edition: str | None
    paths: tuple[str, ...]
    fields: tuple[str, ...]
    defaults: tuple[str, ...]
    previous_reference: bool
    exception_scope: str | None
    kind: str            # migration | deprecation | exception | default | link | generic
    anchor: str | None = None
    links: tuple[str, ...] = field(default_factory=tuple)


def _classify(sentence, exception_scope):
    if exception_scope:
        return 'exception'
    if any(hint in sentence for hint in MIGRATION_HINTS):
        return 'migration'
    if any(hint in sentence for hint in DEPRECATION_HINTS):
        return 'deprecation'
    if DEFAULT_RE.search(sentence):
        return 'default'
    if '段落' in sentence or '锚点' in sentence or '见 ' in sentence or '参见' in sentence:
        return 'link'
    return 'generic'


def extract_statements(record, product=None, anchor=None, edition_hint=None, index=0):
    """把一条原文记录拆成若干 Statement；拆分后仍保留来源、修订号与原句。

    edition_hint 用于小节标题已写明版本、句中不再重复版本的情况；句中出现的
    显式版本（如迁移说明里的 v2）优先级高于标题继承值。
    """
    text = normalize_text(record['text'])
    sentences = [part.strip() for part in SENTENCE_SPLIT_RE.split(text) if part.strip()]
    statements = []
    # 版本可能写在相邻句子里：同一条记录内沿用最近出现的版本与产品名
    current_edition = edition_hint
    current_product = product
    for offset, sentence in enumerate(sentences):
        edition_match = EDITION_RE.search(sentence)
        if edition_match:
            current_edition = edition_match.group(0)
        paths = tuple(PATH_RE.findall(sentence))
        fields = tuple(dict.fromkeys(
            FIELD_GLOSSARY[word] for word in FIELD_GLOSSARY if word in sentence
        ))
        fields += tuple(token[1:] for token in FIELD_RE.findall(sentence) if token[1:] not in fields)
        defaults = tuple(DEFAULT_RE.findall(sentence))
        exception_match = EXCEPTION_RE.search(sentence)
        exception_scope = exception_match.group('scope') if exception_match else None
        links = tuple(
            match for match in re.findall(r'段落\s*([A-Za-z0-9\-_]+)|锚点\s*([A-Za-z0-9\-_]+)', sentence)
            for match in match if match
        )
        statements.append(Statement(
            statement_id=f"{record['record_id']}#{index + offset}",
            source=record['source'],
            revision=record['revision'],
            sentence=sentence,
            product=current_product,
            edition=current_edition,
            paths=paths,
            fields=tuple(dict.fromkeys(fields)),
            defaults=tuple(dict.fromkeys(defaults)),
            previous_reference=bool(PREVIOUS_RE.search(sentence)),
            exception_scope=exception_scope,
            kind=_classify(sentence, exception_scope),
            anchor=anchor,
            links=tuple(dict.fromkeys(links)),
        ))
    return statements


def extract_all(records, product=None, page_texts=None):
    """汇总迁移说明类记录与各页面正文的陈述。"""
    all_statements = []
    counter = 0
    for record in records:
        batch = extract_statements(record, product=product, index=counter)
        all_statements.extend(batch)
        counter += len(batch) or 1
    for anchor, row in (page_texts or {}).items():
        # 锚点以页面声明的稳定 anchor 字段为准，而非字典键；章节重排后键序会变
        stable_anchor = row.get('anchor', anchor)
        record = {
            'record_id': f'page:{stable_anchor}',
            'source': f'guide-page:{stable_anchor}',
            'revision': row.get('revision', 1),
            'text': row['text'],
        }
        batch = extract_statements(record, product=row.get('product', product),
                                   anchor=stable_anchor, edition_hint=row.get('edition'),
                                   index=counter)
        all_statements.extend(batch)
        counter += len(batch) or 1
    return all_statements
