import json
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).parents[1]
ENV = {'PYTHONPATH': str(PROJECT / 'src')}


def _run(*args):
    return subprocess.run(
        [sys.executable, '-m', 'nlp_software_doc_ownership.publisher_cli', *args],
        cwd=PROJECT, capture_output=True, text=True, env={**ENV}, check=True)


def test_cli_review_edition_reports_blockers_and_carry_over():
    result = _run('review', 'Mercury', 'v2')
    data = json.loads(result.stdout)
    assert data['edition'] == 'v2'
    assert data['publishable'] is False
    anchors = {report['page']['anchor'] for report in data['pages']}
    assert {'follow-export', 'legacy-gateway-export', 'follow-export-mixed'} <= anchors
    assert [item['evidence']['link'] for item in data['broken_cross_links']] == ['status-v1']


def test_cli_review_page_and_legacy_commands_coexist():
    page = json.loads(_run('review-page', 'export-v2').stdout)
    assert [item['code'] for item in page['blocking_findings']] == ['STALE_FIELD_REFERENCE']
    receipt = json.loads(_run('receipt', 'mercury-v1').stdout)
    assert receipt[0]['calls'][0]['result'] == ['job_id']
    check = json.loads(_run('check', 'export-v2').stdout)
    assert check['missing'] == ['文件交付组']
