"""按读者选定的产品版本核对说明、多步调用关联与核批效力。

设计要点（对应维护人员的核批需要）：
* 调用仍适用但接不到正确输入（BROKEN_BINDING）与接口已弃用（DEPRECATED_ENDPOINT）
  是两类不同 finding，处置方式不同；
* “除……外”的例外只豁免其限定的用法（按调用标记与例外范围匹配）；
* 重排章节后锚点仍可用；“前一个接口”有多个候选时保留原句与候选，先隔离不删改；
* 已刊发批准只在契约指纹与示例用途指纹都未变时沿用；迁移声明与跨步骤改动
  会要求相应负责人重新确认；
* 跨段落链接必须在读者选定版本中存在；替换轨迹记录当前版本哪一步因何变更。
"""
import re
from dataclasses import dataclass, field as dc_field
from types import SimpleNamespace

from .statements import extract_all

# finding 代码 -> 维护人员看到的处置类别
BLOCKING_CODES = {
    'UNKNOWN_ARGUMENT', 'BROKEN_BINDING', 'DEPRECATED_ENDPOINT',
    'UNKNOWN_ENDPOINT', 'RESULT_FIELD_MISMATCH', 'STALE_FIELD_REFERENCE',
    'BROKEN_CROSS_LINK',
}
# 隔离区只放非阻断性的待确认陈述；阻断项的原句已随 finding 保留，避免重复列示
QUARANTINE_CODES = {'AMBIGUOUS_PREVIOUS_STEP'}


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str              # blocker | warning | info
    message: str
    source: str
    sentence: str | None = None
    anchor: str | None = None
    step: int | None = None
    endpoint: str | None = None
    field: str | None = None
    candidates: tuple = ()
    evidence: dict = dc_field(default_factory=dict)

    def to_dict(self):
        return {key: value for key, value in self.__dict__.items()
                if value not in (None, (), {})}


@dataclass
class ApprovalDecision:
    owner: str
    status: str                # carried | reconfirm_required | missing
    reason: str
    evidence: dict = dc_field(default_factory=dict)

    def to_dict(self):
        return dict(self.__dict__)


@dataclass
class ReplacementTrace:
    anchor: str
    step: int
    endpoint: str
    changed: str
    from_value: str | None
    to_value: str | None
    reason_statement: str | None
    source: str | None

    def to_dict(self):
        return dict(self.__dict__)


class GuideReviewer:
    def __init__(self, registry, statements, deprecated=None, edition_anchors=None,
                 pages=None, publisher=None):
        self.registry = registry
        self.statements = statements
        # deprecated: {(product, edition, path): status}，status 通常为 deprecated
        self.deprecated = deprecated or {}
        self.edition_anchors = edition_anchors or {}
        self.pages = pages or {}
        self.publisher = publisher

    # ------------------------------------------------------------------ #
    # 单页审校
    # ------------------------------------------------------------------ #
    def review_page(self, page):
        findings, traces = self._check_calls(page)
        findings.extend(self._check_narrative(page))
        findings.extend(self._check_links(page))
        decisions = self._approval_decisions(page, findings)
        blocking = [item.to_dict() for item in findings if item.code in BLOCKING_CODES]
        quarantine = [item.to_dict() for item in findings if item.code in QUARANTINE_CODES]
        pending = [decision.to_dict() for decision in decisions
                   if decision.status != 'carried']
        return {
            'page': _page_ref(page),
            'publishable': not blocking and not pending,
            'blocking_findings': blocking,
            'quarantined_statements': quarantine,
            'other_findings': [item.to_dict() for item in findings
                               if item.code not in BLOCKING_CODES
                               and item.code not in QUARANTINE_CODES],
            'approvals': [decision.to_dict() for decision in decisions],
            'defaults': self._defaults_for(page),
            'replacement_traces': [trace.to_dict() for trace in traces],
        }

    def review_edition(self, product, edition):
        """面向指定版本发布的整版审校：每页核对，并检查跨段落链接。"""
        pages = [page for page in self.pages.values()
                 if page.product == product and page.edition == edition]
        reports = [self.review_page(page) for page in pages]
        broken_links = []
        valid_anchors = set(self.edition_anchors.get((product, edition), ()))
        seen_links = set()
        for statement in self.statements:
            if statement.edition not in (None, edition):
                continue
            for link in statement.links:
                if link in valid_anchors or link in seen_links:
                    continue
                seen_links.add(link)
                broken_links.append(Finding(
                    code='BROKEN_CROSS_LINK', severity='blocker',
                    message=f'链接锚点 {link} 在 {product} {edition} 中不存在，该版本读者无法照着操作',
                    source=statement.source, sentence=statement.sentence,
                    anchor=statement.anchor,
                    evidence={'link': link, 'available': sorted(valid_anchors)},
                ).to_dict())
        return {
            'product': product,
            'edition': edition,
            'pages': reports,
            'broken_cross_links': broken_links,
            'publishable': (not broken_links
                            and all(report['publishable'] for report in reports)),
        }

    # ------------------------------------------------------------------ #
    # 多步调用核验：弃用与“接不到正确输入”分开报告
    # ------------------------------------------------------------------ #
    def _check_calls(self, page):
        findings = []
        traces = []
        available = {}
        prior = self._prior_page(page)
        prior_bindings = _binding_basis(prior)
        # 本页可豁免例外的范围（“除旧网关外”只影响它限定的用法）
        exception_scopes = {
            statement.exception_scope
            for statement in self.statements
            if statement.exception_scope and _statement_applies(statement, page)
        }
        for index, call in enumerate(page.calls):
            step = index + 1
            endpoint = self._resolve_endpoint(page, call, step, findings)
            if endpoint is None:
                continue
            if self._is_deprecated(page, call):
                findings.append(Finding(
                    code='DEPRECATED_ENDPOINT', severity='blocker',
                    message=f'{call.method} {call.path} 在 {page.edition} 已弃用，'
                            f'接口本身不再适用，需要替换接口而非仅修正参数',
                    source='contract-registry', anchor=page.anchor, step=step,
                    endpoint=call.path,
                    evidence={'owner': endpoint.owner},
                ))
            exempt = _call_exempt(call, exception_scopes)
            if exempt:
                findings.append(Finding(
                    code='EXCEPTION_APPLIES', severity='info',
                    message=f'第 {step} 步属于例外用法（{exempt}），例外范围内的旧字段说明保留',
                    source='guide-page', anchor=page.anchor, step=step,
                    endpoint=call.path, evidence={'exception_scope': exempt},
                ))
            for argument in call.arguments:
                field_name, delimiter, binding = argument.partition('=')
                if not delimiter or field_name not in endpoint.accepts:
                    findings.append(Finding(
                        code='UNKNOWN_ARGUMENT', severity='blocker',
                        message=f'{call.path} 不接受参数 {field_name}',
                        source='guide-page', anchor=page.anchor, step=step,
                        endpoint=call.path, field=field_name,
                    ))
                    continue
                if binding.startswith('$'):
                    variable = binding[1:]
                    if variable not in available:
                        # 调用本身仍适用，只是拿不到正确输入——与弃用明确区分
                        findings.append(Finding(
                            code='BROKEN_BINDING', severity='blocker',
                            message=(f'{call.path} 的 {field_name} 引用 ${variable}，'
                                     f'但此前的调用在 {page.edition} 不返回该字段；'
                                     f'接口未弃用，需改读实际返回字段'),
                            source='guide-page', anchor=page.anchor, step=step,
                            endpoint=call.path, field=variable,
                            evidence={'available_fields': sorted(available)},
                        ))
                    elif not exempt:
                        current_binding = f'${variable}'
                        prior_binding = prior_bindings.get(
                            (step, call.path, field_name))
                        # 只有相对已刊发版本确实发生变化，才记入替换轨迹
                        if prior_binding is not None and prior_binding != current_binding:
                            traces.append(ReplacementTrace(
                                anchor=page.anchor, step=step, endpoint=call.path,
                                changed='cross-step-binding',
                                from_value=prior_binding, to_value=current_binding,
                                reason_statement=self._migration_reason(page, variable),
                                source='migration-notice',
                            ))
            for result_field in call.result:
                if result_field not in endpoint.returns:
                    findings.append(Finding(
                        code='RESULT_FIELD_MISMATCH', severity='blocker',
                        message=f'{call.path} 在 {page.edition} 不返回 {result_field}',
                        source='contract-registry', anchor=page.anchor, step=step,
                        endpoint=call.path, field=result_field,
                        evidence={'returns': list(endpoint.returns)},
                    ))
                else:
                    available.setdefault(result_field, (step, call.path))
            self._trace_field_change(page, call, endpoint, step, traces)
        return findings, traces

    def _resolve_endpoint(self, page, call, step, findings):
        try:
            return self.registry.resolve(page.product, page.edition, call.method, call.path)
        except ValueError:
            findings.append(Finding(
                code='UNKNOWN_ENDPOINT', severity='blocker',
                message=f'{call.method} {call.path} 未在 {page.product}/{page.edition} 登记',
                source='contract-registry', anchor=page.anchor, step=step,
                endpoint=call.path,
            ))
            return None

    def _is_deprecated(self, page, call):
        status = self.deprecated.get((page.product, page.edition, call.path))
        return status == 'deprecated'

    # ------------------------------------------------------------------ #
    # 自然语言陈述核对
    # ------------------------------------------------------------------ #
    def _check_narrative(self, page):
        findings = []
        returned_fields = self._returned_fields(page)
        ambiguous_candidates = self._previous_candidates(page)
        for statement in self.statements:
            if not _statement_applies(statement, page):
                continue
            # 迁移陈述本身在讲“旧字段被新字段替换”，它的旧字段引用不是过时说明
            if statement.kind == 'migration':
                findings.append(Finding(
                    code='MIGRATION_NOTE', severity='info',
                    message='迁移陈述记录字段替换关系，作为替换轨迹的依据，不按过时引用处理',
                    source=statement.source, sentence=statement.sentence,
                    anchor=page.anchor,
                    evidence={'fields': list(statement.fields)},
                ))
                continue
            # 逐字段判断：同一句中“编号/id”仍有效，不应掩盖已过时的 job_id
            for field_name in statement.fields:
                if field_name in returned_fields or field_name in page_accepted(page):
                    continue
                # 例外只豁免它限定的用法：本页没有被该例外覆盖的调用时不豁免
                if statement.exception_scope and not self._exception_covers(statement, page):
                    findings.append(Finding(
                        code='STALE_FIELD_REFERENCE', severity='blocker',
                        message=(f'说明仍引用 {page.edition} 不再返回的字段 {field_name}，'
                                 f'且本页用法不属于例外“{statement.exception_scope}”；'
                                 f'读者照此示例无法完成后续调用，原句先隔离保留'),
                        source=statement.source, sentence=statement.sentence,
                        anchor=page.anchor, field=field_name,
                        evidence={'returned_fields': sorted(returned_fields),
                                  'exception_scope': statement.exception_scope},
                    ))
                    continue
                if statement.exception_scope:
                    continue
                findings.append(Finding(
                    code='STALE_FIELD_REFERENCE', severity='blocker',
                    message=(f'说明仍引用 {page.edition} 不再返回的字段 {field_name}，'
                             f'读者照此示例无法完成后续调用；原句先隔离保留，待改写后复核'),
                    source=statement.source, sentence=statement.sentence,
                    anchor=page.anchor, field=field_name,
                    evidence={'returned_fields': sorted(returned_fields)},
                ))
            # 只有本页自己使用“上一步/前一个接口”措辞且确有多个前置步骤时才隔离；
            # 逐条陈述判断，避免其他页面的歧义说明牵连本页；
            # “若……不唯一”一类假设句本身是处置规则，不作为待隔离的误导说明
            if (statement.previous_reference and statement.anchor == page.anchor
                    and len(ambiguous_candidates) > 1
                    and not sentence_is_conditional(statement.sentence)):
                findings.append(Finding(
                    code='AMBIGUOUS_PREVIOUS_STEP', severity='warning',
                    message=('“前一个接口”存在多个候选，重排章节后无法确定取哪一步的编号；'
                             '原句先隔离保留，待维护人员确认候选后改写'),
                    source=statement.source, sentence=statement.sentence,
                    anchor=page.anchor,
                    candidates=tuple(ambiguous_candidates),
                ))
            if statement.kind == 'deprecation' and statement.paths:
                for path in statement.paths:
                    if not self._is_deprecated(page, SimpleNamespace(path=path)):
                        findings.append(Finding(
                            code='UNVERIFIED_DEPRECATION_CLAIM', severity='warning',
                            message=f'陈述称 {path} 已弃用，但注册表未标记弃用',
                            source=statement.source, sentence=statement.sentence,
                            anchor=page.anchor, endpoint=path,
                        ))
        return findings

    def _check_links(self, page):
        findings = []
        valid_anchors = set(self.edition_anchors.get((page.product, page.edition), ()))
        for statement in self.statements:
            # 页面级只核对挂在该锚点上的链接；未挂锚点的记录链接由整版审校统一核对
            if statement.anchor != page.anchor:
                continue
            for link in statement.links:
                if link not in valid_anchors:
                    findings.append(Finding(
                        code='BROKEN_CROSS_LINK', severity='blocker',
                        message=(f'段落链接 {link} 在 {page.product} {page.edition} '
                                 f'不可用，读者无法按该版本照着操作'),
                        source=statement.source, sentence=statement.sentence,
                        anchor=page.anchor, evidence={'link': link},
                    ))
        return findings

    # ------------------------------------------------------------------ #
    # 核批效力：契约与示例用途都未变才能沿用旧批准
    # ------------------------------------------------------------------ #
    def _approval_decisions(self, page, findings):
        owners = self._owners(page)
        prior = self._prior_page(page)
        decisions = []
        for owner in owners:
            if prior is None:
                if owner in page.approvals:
                    decisions.append(ApprovalDecision(
                        owner, 'carried', '当前草稿已直接取得该负责人批准',
                        {'approved_on_draft': True}))
                else:
                    decisions.append(ApprovalDecision(
                        owner, 'missing', '无历史刊发可沿用，需新批准'))
                continue
            if owner not in tuple(prior.get('approvals', ())):
                decisions.append(ApprovalDecision(
                    owner, 'missing', '历史刊发中无该负责人的批准',
                    {'prior_publication': prior['publication']}))
                continue
            owner_paths = self._owner_endpoints(page, owner)
            contract_changed = self._contract_changed_for(page, owner_paths, prior)
            usage_changed = (_owner_usage_basis(page, owner_paths)
                             != prior.get('usage_basis_by_owner', {}).get(owner))
            cross_step = self._cross_step_impact(page, findings, owner_paths)
            if contract_changed:
                decisions.append(ApprovalDecision(
                    owner, 'reconfirm_required',
                    '该负责人的接口契约（负责人/入参/返回字段）相对已刊发版本变化，旧批准不自动沿用',
                    {'prior_publication': prior['publication'],
                     'contract_changed': True}))
            elif usage_changed or cross_step:
                decisions.append(ApprovalDecision(
                    owner, 'reconfirm_required',
                    '跨步骤字段关联或示例用途变化，需按迁移说明重新确认',
                    {'prior_publication': prior['publication'],
                     'usage_changed': usage_changed, 'cross_step_impact': cross_step}))
            else:
                decisions.append(ApprovalDecision(
                    owner, 'carried',
                    '针对的契约与示例用途仍成立，沿用历史刊发批准',
                    {'prior_publication': prior['publication']}))
        return decisions

    def _owner_endpoints(self, page, owner):
        paths = set()
        for call in page.calls:
            try:
                endpoint = self.registry.resolve(page.product, page.edition,
                                                  call.method, call.path)
            except ValueError:
                continue
            if endpoint.owner == owner:
                paths.add(f'{call.method} {call.path}')
        return paths

    def _contract_changed_for(self, page, owner_paths, prior):
        """只比较该负责人名下接口在同锚点历史页面中的契约指纹。"""
        for endpoint_key in owner_paths:
            history = _prior_contract_for(prior, endpoint_key)
            if history is None:
                return True
            current = self._current_contract(page, endpoint_key)
            if current is None or history != current:
                return True
        return False

    def _current_contract(self, page, endpoint_key):
        method, path = endpoint_key.split(' ', 1)
        try:
            endpoint = self.registry.resolve(page.product, page.edition, method, path)
        except ValueError:
            return None
        return {'owner': endpoint.owner,
                'accepts': list(endpoint.accepts),
                'returns': list(endpoint.returns)}

    def _cross_step_impact(self, page, findings, owner_paths):
        """跨步骤问题同时影响产出方与消费方两个负责人。"""
        impacted = set()
        for item in findings:
            if item.code != 'BROKEN_BINDING' or item.step is None:
                continue
            call = page.calls[item.step - 1]
            impacted.add(f'{call.method} {call.path}')
            producer = self._producer_of(page, item.field)
            if producer:
                impacted.add(producer)
        return bool(impacted & owner_paths)

    def _producer_of(self, page, field_name):
        for call in page.calls:
            try:
                endpoint = self.registry.resolve(page.product, page.edition,
                                                  call.method, call.path)
            except ValueError:
                continue
            if field_name in endpoint.returns:
                return f'{call.method} {call.path}'
        return None

    # ------------------------------------------------------------------ #
    # 替换轨迹：当前版本的哪一步因什么变更需要替换
    # ------------------------------------------------------------------ #
    def _trace_field_change(self, page, call, endpoint, step, traces):
        prior = self._prior_page(page)
        if prior is None:
            return
        prior_contract = prior.get('contract_basis', {}).get(f'{call.method} {call.path}')
        if not prior_contract:
            return
        removed = [field_name for field_name in prior_contract['returns']
                   if field_name not in endpoint.returns]
        added = [field_name for field_name in endpoint.returns
                 if field_name not in prior_contract['returns']]
        for field_name in removed:
            traces.append(ReplacementTrace(
                anchor=page.anchor, step=step, endpoint=call.path,
                changed='return-field', from_value=field_name,
                to_value=added[0] if added else None,
                reason_statement=self._migration_reason(page, field_name),
                source='migration-notice',
            ))

    def _migration_reason(self, page, field_name):
        for statement in self.statements:
            if statement.kind != 'migration':
                continue
            if statement.edition not in (None, page.edition):
                continue
            if field_name in statement.fields or not statement.fields:
                return statement.sentence
        return None

    # ------------------------------------------------------------------ #
    # 辅助
    # ------------------------------------------------------------------ #
    def _owners(self, page):
        owners = set()
        for call in page.calls:
            try:
                endpoint = self.registry.resolve(page.product, page.edition,
                                                  call.method, call.path)
            except ValueError:
                continue
            owners.add(endpoint.owner)
        return sorted(owners)

    def _returned_fields(self, page):
        fields = set()
        for call in page.calls:
            try:
                endpoint = self.registry.resolve(page.product, page.edition,
                                                  call.method, call.path)
            except ValueError:
                continue
            fields.update(endpoint.returns)
        return fields

    def _previous_candidates(self, page):
        """本页内能够产出“上一步编号”的前置步骤；多于一个即存在歧义。

        重排章节不改变锚点，同页内的步骤顺序仍是确定的；只有同页出现多个
        可产出编号的前置调用时，“前一个接口”才不唯一。候选保留步骤号与接口，
        维护人员可据此回到原句确认。
        """
        candidates = []
        for index, call in enumerate(page.calls[:-1]):
            try:
                endpoint = self.registry.resolve(page.product, page.edition,
                                                  call.method, call.path)
            except ValueError:
                continue
            candidates.append({
                'step': index + 1,
                'endpoint': f'{call.method} {call.path}',
                'returns': list(endpoint.returns),
                'anchor': page.anchor,
            })
        return candidates

    def _defaults_for(self, page):
        results = []
        for statement in self.statements:
            if not (_statement_applies(statement, page) and statement.defaults):
                continue
            field_name = statement.fields[0] if statement.fields else None
            if field_name is None:
                # 默认值可能写在相邻句子里：从句中点名接口的入参补全字段名
                field_name = self._accepted_field_for(page, statement)
            results.append({'field': field_name, 'default': statement.defaults[0],
                            'source': statement.source, 'sentence': statement.sentence})
        return results

    def _accepted_field_for(self, page, statement):
        for call in page.calls:
            if statement.paths and call.path not in statement.paths:
                continue
            try:
                endpoint = self.registry.resolve(page.product, page.edition,
                                                  call.method, call.path)
            except ValueError:
                continue
            if endpoint.accepts:
                return endpoint.accepts[0]
        return None

    def _exception_covers(self, statement, page):
        return any(_call_exempt(call, {statement.exception_scope})
                   for call in page.calls)

    def _prior_page(self, page):
        if self.publisher is None:
            return None
        for publication in self.publisher.publication_ids():
            receipt = self.publisher.receipt(publication)
            for row in receipt:
                if row.get('anchor') != page.anchor:
                    continue
                if row.get('product') != page.product:
                    continue
                prior_page = SimpleNamespace(**{
                    **row, 'calls': [SimpleNamespace(**call) for call in row['calls']],
                })
                return {
                    'publication': publication,
                    'approvals': row.get('approvals', ()),
                    'contract_basis': _contract_basis(self.registry, row,
                                                      row['product'], row['edition']),
                    'usage_basis': _usage_basis(prior_page),
                    'usage_basis_by_owner': self._usage_basis_by_owner(row, prior_page),
                }
        return None

    def _usage_basis_by_owner(self, row, prior_page):
        """历史页面中每个负责人名下的用途指纹，供逐负责人沿用判断。"""
        basis = {}
        for call in row['calls']:
            try:
                endpoint = self.registry.resolve(row['product'], row['edition'],
                                                  call['method'], call['path'])
            except ValueError:
                continue
            basis.setdefault(endpoint.owner, []).append(
                (call['method'], call['path'], tuple(call['arguments']),
                 tuple(call['result'])))
        return {owner: tuple(items) for owner, items in basis.items()}


# ---------------------------------------------------------------------- #
# 模块级辅助
# ---------------------------------------------------------------------- #
def _call_exempt(call, exception_scopes):
    """例外只作用于它限定的用法：调用标记与例外范围词匹配才豁免。"""
    tags = set(getattr(call, 'tags', ()) or ())
    for scope in exception_scopes:
        if not scope:
            continue
        token = re.sub(r'[^\w㐀-鿿]+', '', scope)
        if token and token in {re.sub(r'[^\w㐀-鿿]+', '', tag) for tag in tags}:
            return scope
    return None


def sentence_is_conditional(sentence):
    """假设/条件句（“若……则/先……”）描述处置规则，而非可照做的误导说明。"""
    return sentence.startswith(('若', '如果', '假如'))


def _statement_applies(statement, page):
    if statement.edition is not None and statement.edition != page.edition:
        return False
    if statement.product is not None and statement.product != page.product:
        return False
    if statement.anchor is not None and statement.anchor != page.anchor:
        return False
    # 记录里点名了接口，而本页没有该接口，则陈述不约束本页
    if statement.paths and not any(
            call.path in statement.paths for call in page.calls):
        return False
    return True


def page_accepted(page):
    fields = set()
    for call in page.calls:
        for argument in call.arguments:
            name, delimiter, _ = argument.partition('=')
            if delimiter:
                fields.add(name)
    return fields


def _page_ref(page):
    return {'product': page.product, 'edition': page.edition, 'anchor': page.anchor}


def _usage_basis(page):
    """示例用途指纹：调用顺序、参数绑定与读取的返回字段。"""
    return tuple(
        (call.method, call.path, tuple(call.arguments), tuple(call.result))
        for call in page.calls
    )


def _owner_usage_basis(page, owner_paths):
    """当前页面中某负责人名下接口的用途指纹（保持调用顺序）。"""
    return tuple(
        (call.method, call.path, tuple(call.arguments), tuple(call.result))
        for call in page.calls
        if f'{call.method} {call.path}' in owner_paths
    )


def _binding_basis(prior):
    """历史页面里每个 (步骤, 接口, 参数名) 使用的绑定，用于跨步骤改动比对。"""
    if prior is None:
        return {}
    basis = {}
    for step, call in enumerate(prior.get('usage_basis', ()), start=1):
        method, path, arguments, _ = call
        for argument in arguments:
            field_name, delimiter, binding = argument.partition('=')
            if delimiter:
                basis[(step, path, field_name)] = binding
    return basis


def _prior_contract_for(prior, endpoint_key):
    return prior.get('contract_basis', {}).get(endpoint_key)


def _contract_basis(registry, row, product, edition):
    basis = {}
    for call in row['calls']:
        try:
            endpoint = registry.resolve(product, edition, call['method'], call['path'])
        except ValueError:
            continue
        basis[f"{call['method']} {call['path']}"] = {
            'owner': endpoint.owner,
            'accepts': list(endpoint.accepts),
            'returns': list(endpoint.returns),
        }
    return basis


def build_reviewer(guide_data, records, registry, pages, publisher):
    """从 guide.json、原文记录与已刊发目录组装审校器。"""
    statements = extract_all(
        records,
        product=guide_data.get('product'),
        page_texts={anchor: row for anchor, row in guide_data['pages'].items()},
    )
    deprecated = {}
    for row in guide_data.get('deprecations', ()):
        deprecated[(row['product'], row['edition'], row['path'])] = row.get('status', 'deprecated')
    edition_anchors = {}
    for anchor, row in guide_data['pages'].items():
        edition_anchors.setdefault((row['product'], row['edition']), set()).add(anchor)
    for row in guide_data.get('sections', ()):
        edition_anchors.setdefault((row['product'], row['edition']), set()).add(row['anchor'])
    return GuideReviewer(registry, statements, deprecated,
                         {key: tuple(value) for key, value in edition_anchors.items()},
                         pages, publisher)
