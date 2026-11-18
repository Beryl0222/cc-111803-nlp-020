from dataclasses import dataclass


@dataclass(frozen=True)
class Endpoint:
    product: str
    edition: str
    method: str
    path: str
    owner: str
    accepts: tuple[str, ...]
    returns: tuple[str, ...]

    @property
    def key(self):
        return self.product, self.edition, self.method, self.path


class ContractRegistry:
    def __init__(self, endpoints):
        self.entries = {}
        for endpoint in endpoints:
            if endpoint.key in self.entries:
                raise ValueError(f'重复的接口契约：{endpoint.key}')
            self.entries[endpoint.key] = endpoint

    def resolve(self, product, edition, method, path):
        key = product, edition, method, path
        if key not in self.entries:
            raise ValueError(f'未登记接口 {method} {path}，版本 {product}/{edition}')
        return self.entries[key]
