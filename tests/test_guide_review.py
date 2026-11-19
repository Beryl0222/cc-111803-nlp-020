"""版本化指南审校：自然语言/迁移说明、多步关联、例外与核批效力。"""
from dataclasses import replace
from pathlib import Path

import pytest

from nlp_software_doc_ownership.contracts import ContractRegistry, Endpoint
from nlp_software_doc_ownership.examples import Call
from nlp_software_doc_ownership.publisher_cli import load_review_inputs, open_guide
from nlp_software_doc_ownership.review import build_reviewer
from nlp_software_doc_ownership.statements import extract_all


@pytest.fixture
def reviewer():
    pages, publisher = open_guide(Path(__file__).parents[1] / 'fixtures' / 'guide.json')
    guide_data, records = load_review_inputs(
        Path(__file__).parents[1] / 'fixtures' / 'guide.json',
        Path(__file__).parents[1] / 'fixtures' / 'records.json',
        Path(__file__).parents[1] / 'fixtures' / 'business.json')
    registry = ContractRegistry(Endpoint(**row) for row in guide_data['endpoints'])
    return build_reviewer(guide_data, records, registry, pages, publisher), pages, publisher


def codes(report, bucket):
    return [item['code'] for item in report[bucket]]


def test_stale_narrative_field_blocked_but_calls_remain_valid(reviewer):
    review, pages, _ = reviewer
    report = review.review_page(pages['export-v2'])
    stale = [item for item in report['blocking_findings']
             if item['code'] == 'STALE_FIELD_REFERENCE']
    # 指南正文仍让读者读旧字段 job_id，但示例调用本身已改用 $ticket
    assert len(stale) == 1 and stale[0]['field'] == 'job_id'
    assert stale[0]['sentence'].startswith('状态检查取上一步返回的作业编号')
    assert 'BROKEN_BINDING' not in codes(report, 'blocking_findings')
    assert report['publishable'] is False


def test_broken_binding_is_distinct_from_deprecation(reviewer):
    review, pages, _ = reviewer
    # 状态接口未弃用，只是示例仍引用不再返回的 job_id
    broken_page = replace(
        pages['export-v2'],
        calls=(pages['export-v2'].calls[0],
               Call('GET', '/status', ('id=$job_id',), ('state',))))
    report = review.review_page(broken_page)
    binding = [item for item in report['blocking_findings']
               if item['code'] == 'BROKEN_BINDING']
    assert len(binding) == 1
    assert binding[0]['endpoint'] == '/status'
    assert binding[0]['field'] == 'job_id'
    assert 'DEPRECATED_ENDPOINT' not in codes(report, 'blocking_findings')
    assert '接口未弃用' in binding[0]['message']


def test_deprecated_endpoint_reported_separately(reviewer):
    review, pages, _ = reviewer
    report = review.review_page(pages['export-v1'])
    deprecated = [item for item in report['blocking_findings']
                  if item['code'] == 'DEPRECATED_ENDPOINT']
    assert len(deprecated) == 1 and deprecated[0]['endpoint'] == '/export'
    # 状态接口仍活跃，不应被标记弃用
    assert all(item.get('endpoint') != '/status' for item in deprecated)


def test_exception_scope_only_exempts_tagged_usage(reviewer):
    review, pages, _ = reviewer
    gateway = review.review_page(pages['gateway-v2'])
    assert gateway['publishable'] is True
    assert codes(gateway, 'other_findings').count('EXCEPTION_APPLIES') == 2
    # 普通 v2 页没有旧网关标记：例外陈述不豁免它，本页过时的 job_id 仍被拦截
    normal = review.review_page(pages['export-v2'])
    stale = [item for item in normal['blocking_findings']
             if item['code'] == 'STALE_FIELD_REFERENCE']
    assert len(stale) == 1 and stale[0]['field'] == 'job_id'
    # 例外陈述本身在普通页不产生豁免信息
    assert not any(item['code'] == 'EXCEPTION_APPLIES'
                   for item in normal['other_findings'])


def test_ambiguous_previous_step_quarantines_original_sentence(reviewer):
    review, pages, _ = reviewer
    report = review.review_page(pages['follow-export-mixed'])
    quarantined = report['quarantined_statements']
    # 只有真正的歧义指令被隔离；“若……不唯一”假设句是处置规则，不重复隔离
    assert len(quarantined) == 1
    candidates = quarantined[0]['candidates']
    assert {item['endpoint'] for item in candidates} == {
        'GET /export', 'GET /export/gateway'}
    assert quarantined[0]['sentence'].startswith('前一个接口返回票据编号')
    # 唯一前置步骤的页面不产生歧义隔离
    single = review.review_page(pages['export-v2'])
    assert codes(single, 'quarantined_statements') == []


def test_anchor_survives_reorder_and_uses_declared_anchor(reviewer):
    review, pages, _ = reviewer
    anchors = {statement.anchor for statement in review.statements
               if statement.anchor}
    # 页面陈述挂在稳定锚点上，而非 JSON 字典键（export-v2 是键，锚点是 follow-export）
    assert 'follow-export' in anchors and 'follow-export-mixed' in anchors
    assert 'export-v2-mixed' not in anchors


def test_approval_carried_only_when_contract_and_usage_hold(reviewer):
    review, pages, _ = reviewer
    report = review.review_page(pages['export-v2'])
    by_owner = {item['owner']: item for item in report['approvals']}
    # /status 契约未变，但跨步骤读取从 $job_id 改成 $ticket，状态组需重新确认
    assert by_owner['作业状态组']['status'] == 'reconfirm_required'
    assert by_owner['作业状态组']['evidence']['usage_changed'] is True
    # /export 负责人更换，文件交付组在历史刊发中没有批准
    assert by_owner['文件交付组']['status'] == 'missing'
    # 例外页两个负责人当前草稿已批准，直接沿用
    gateway = review.review_page(pages['gateway-v2'])
    assert all(item['status'] == 'carried' for item in gateway['approvals'])


def test_unchanged_contract_keeps_prior_approval(reviewer):
    review, pages, publisher = reviewer
    # v1 已刊发；同锚点的 v1 草稿契约与用途都未变时，批准应沿用
    report = review.review_page(pages['export-v1'])
    by_owner = {item['owner']: item for item in report['approvals']}
    assert by_owner['作业状态组']['status'] == 'carried'
    assert by_owner['数据导出组']['status'] == 'carried'


def test_replacement_trace_links_change_to_migration_statement(reviewer):
    review, pages, _ = reviewer
    report = review.review_page(pages['export-v2'])
    traces = report['replacement_traces']
    field_change = next(item for item in traces if item['changed'] == 'return-field')
    binding_change = next(item for item in traces if item['changed'] == 'cross-step-binding')
    assert (field_change['from_value'], field_change['to_value']) == ('job_id', 'ticket')
    assert (binding_change['from_value'], binding_change['to_value']) == ('$job_id', '$ticket')
    assert '替换为票据编号' in field_change['reason_statement']


def test_edition_cross_link_must_work_in_selected_edition(reviewer):
    review, _, _ = reviewer
    v2 = review.review_edition('Mercury', 'v2')
    assert [item['evidence']['link'] for item in v2['broken_cross_links']] == ['status-v1']
    assert v2['publishable'] is False
    v1 = review.review_edition('Mercury', 'v1')
    assert v1['broken_cross_links'] == []


def test_default_value_resolves_from_adjacent_sentence(reviewer):
    review, pages, _ = reviewer
    report = review.review_page(pages['export-v2'])
    defaults = report['defaults']
    assert defaults and defaults[0]['default'] == '100'
    # 句中没有字段词时，从相邻句子点名接口的入参补全为 limit
    assert defaults[0]['field'] == 'limit'


def test_receipt_keeps_original_publication_lookup(reviewer):
    _, _, publisher = reviewer
    receipt = publisher.receipt('mercury-v1')
    assert receipt[0]['edition'] == 'v1'
    assert receipt[0]['calls'][0]['result'] == ['job_id']
    assert 'mercury-v1' in publisher.publication_ids()


def test_statement_extraction_identifies_endpoint_field_exception():
    records = [{
        'record_id': 'n1', 'source': 'migration-notice', 'revision': 1,
        'text': '除旧网关外，v2 的 /export/gateway 仍返回作业编号，其余不再返回 job_id。',
    }]
    statements = extract_all(records)
    statement = statements[0]
    assert statement.kind == 'exception'
    assert statement.exception_scope == '旧网关'
    assert statement.edition == 'v2'
    assert '/export/gateway' in statement.paths
    assert 'job_id' in statement.fields
