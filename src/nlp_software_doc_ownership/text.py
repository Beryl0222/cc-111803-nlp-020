import re


def normalize_text(value):
    if not isinstance(value, str):
        raise TypeError('文本必须是字符串')
    return re.sub(r'\s+', ' ', value).strip()


def tokens(value):
    return re.findall(r'[A-Za-z0-9]+|[\u3400-\u9fff]', value.casefold())
