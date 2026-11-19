from dataclasses import dataclass


@dataclass(frozen=True)
class Call:
    method: str
    path: str
    arguments: tuple[str, ...]
    result: tuple[str, ...]
    # 用法标记：用于匹配“除旧网关外”一类例外的限定范围；旧数据缺省为空
    tags: tuple[str, ...] = ()


class ExampleCheck:
    def __init__(self, registry):
        self.registry = registry

    def verify(self, product, edition, calls):
        available = set()
        owners = set()
        for call in calls:
            endpoint = self.registry.resolve(product, edition, call.method, call.path)
            owners.add(endpoint.owner)
            for argument in call.arguments:
                field, delimiter, binding = argument.partition('=')
                if not delimiter or field not in endpoint.accepts:
                    raise ValueError(f'{call.path} 不接受示例参数 {field}')
                if binding.startswith('$') and binding[1:] not in available:
                    raise ValueError(f'{call.path} 引用的变量 {binding} 还未返回')
            for field in call.result:
                if field not in endpoint.returns:
                    raise ValueError(f'{call.path} 不返回示例中的 {field}')
                available.add(field)
        return sorted(owners)
