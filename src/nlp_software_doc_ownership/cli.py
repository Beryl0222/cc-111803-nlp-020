import argparse
import json
from pathlib import Path

from .repository import JsonRepository
from .workflow import TextWorkflow


def main(argv=None):
    parser = argparse.ArgumentParser(description='本地文本记录工作区')
    parser.add_argument('action', choices=['ingest', 'list'])
    parser.add_argument('input', nargs='?')
    parser.add_argument('--source')
    args = parser.parse_args(argv)
    workflow = TextWorkflow(JsonRepository('var/records.json'))
    if args.action == 'ingest':
        if not args.input:
            parser.error('ingest 需要输入 JSON 文件')
        values = json.loads(Path(args.input).read_text(encoding='utf-8'))
        result = workflow.ingest(values)
    else:
        result = workflow.list_records(args.source)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
