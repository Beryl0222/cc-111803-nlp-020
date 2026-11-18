from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass

from .examples import Call


@dataclass(frozen=True)
class Page:
    product: str
    edition: str
    anchor: str
    text: str
    calls: tuple[Call, ...]
    approvals: tuple[str, ...]


class DocPublisher:
    def __init__(self, checker):
        self.checker = checker
        self._catalog = {}

    def check(self, page):
        owners = self.checker.verify(page.product, page.edition, page.calls)
        missing = sorted(set(owners) - set(page.approvals))
        return {'owners': owners, 'missing': missing, 'publishable': not missing}

    def publish(self, publication, pages):
        pages = tuple(pages)
        if publication in self._catalog:
            raise ValueError('发布编号已存在')
        counts = Counter((page.product, page.edition, page.anchor) for page in pages)
        if any(count > 1 for count in counts.values()):
            raise ValueError('同一产品和版本中出现重复文档锚点')
        if any(not self.check(page)['publishable'] for page in pages):
            raise ValueError('部分说明仍待负责人核批')
        self._catalog[publication] = [asdict(page) for page in pages]

    def receipt(self, publication):
        return deepcopy(self._catalog[publication])
