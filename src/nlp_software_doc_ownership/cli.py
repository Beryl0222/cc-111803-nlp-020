import argparse
import json
from pathlib import Path

from .repository import JsonRepository
from .workflow import TextWorkflow


def main(argv=None):
    parser = argparse.ArgumentParser(description='本地文本记录工作区')
    parser.add_argument('action', choices=['ingest', 'list', 'business'])
    parser.add_argument('input', nargs='?')
    parser.add_argument('--source')
    parser.add_argument('--business-file', default='fixtures/business.json')
    args = parser.parse_args(argv)
    workflow = TextWorkflow(JsonRepository('var/records.json'))
    if args.action == 'ingest':
        if not args.input:
            parser.error('ingest 需要输入 JSON 文件')
        values = json.loads(Path(args.input).read_text(encoding='utf-8'))
        result = workflow.ingest(values)
    elif args.action == 'business':
        result = workflow.business_summary(args.business_file)
    else:
        result = workflow.list_records(args.source)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
