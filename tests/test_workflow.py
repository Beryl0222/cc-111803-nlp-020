import json

from nlp_software_doc_ownership.repository import JsonRepository
from nlp_software_doc_ownership.workflow import TextWorkflow


def test_ingest_normalizes_and_persists_records(tmp_path):
    repository = JsonRepository(tmp_path / 'records.json')
    workflow = TextWorkflow(repository)
    result = workflow.ingest([{'record_id': 'r1', 'source': 'local', 'revision': 1, 'text': '  中文\n text  '}])
    assert result == {'received': 1, 'stored': 1}
    assert workflow.list_records() == [{'record_id': 'r1', 'source': 'local', 'revision': 1, 'text': '中文 text', 'tokens': ['中', '文', 'text']}]
    assert json.loads((tmp_path / 'records.json').read_text(encoding='utf-8'))[0]['record_id'] == 'r1'


def test_source_filter_uses_record_metadata(tmp_path):
    workflow = TextWorkflow(JsonRepository(tmp_path / 'records.json'))
    workflow.ingest([{'record_id': 'r1', 'source': 'a', 'revision': 1, 'text': '甲'}, {'record_id': 'r2', 'source': 'b', 'revision': 1, 'text': '乙'}])
    assert [row['record_id'] for row in workflow.list_records('b')] == ['r2']


def test_business_view_uses_registered_facts():
    from pathlib import Path
    project = Path(__file__).resolve().parents[1]
    workflow = TextWorkflow(JsonRepository(project / 'var' / 'records.json'))
    assert workflow.business_summary(project / 'fixtures' / 'business.json') == ['EX-1']
