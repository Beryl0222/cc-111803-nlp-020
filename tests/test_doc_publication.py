from dataclasses import replace
from pathlib import Path

import pytest

from nlp_software_doc_ownership.publisher_cli import open_guide


@pytest.fixture
def guide():
    return open_guide(Path(__file__).parents[1] / 'fixtures' / 'guide.json')


def test_changed_interface_owner_prevents_publish_until_approved(guide):
    pages, publisher = guide
    draft = pages['export-v2']
    assert publisher.check(draft)['missing'] == ['文件交付组']
    with pytest.raises(ValueError, match='部分说明'):
        publisher.publish('mercury-v2', [draft])
    publisher.publish('mercury-v2', [replace(draft, approvals=('文件交付组', '作业状态组'))])
    assert 'ticket' in publisher.receipt('mercury-v2')[0]['calls'][0]['result']
    assert 'job_id' in publisher.receipt('mercury-v1')[0]['calls'][0]['result']


def test_unavailable_binding_fails_even_with_valid_endpoint(guide):
    pages, publisher = guide
    draft = pages['export-v2']
    calls = draft.calls[0], pages['export-v1'].calls[1]
    with pytest.raises(ValueError, match='变量'):
        publisher.check(replace(draft, calls=calls))


def test_published_page_receipt_is_independent(guide):
    _, publisher = guide
    receipt = publisher.receipt('mercury-v1')
    receipt[0]['text'] = '替换'
    assert publisher.receipt('mercury-v1')[0]['text'] != '替换'
