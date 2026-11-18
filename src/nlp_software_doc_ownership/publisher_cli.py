import argparse
import json
from pathlib import Path

from .contracts import ContractRegistry, Endpoint
from .editions import DocPublisher, Page
from .examples import Call, ExampleCheck


def open_guide(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    registry = ContractRegistry(Endpoint(**row) for row in data['endpoints'])
    pages = {}
    for anchor, row in data['pages'].items():
        page_data = dict(row)
        page_data['calls'] = tuple(Call(**call) for call in row['calls'])
        pages[anchor] = Page(**page_data)
    publisher = DocPublisher(ExampleCheck(registry))
    for version, anchors in data['publications'].items():
        publisher.publish(version, (pages[anchor] for anchor in anchors))
    return pages, publisher


def main(argv=None):
    parser = argparse.ArgumentParser(description='接口文档核批')
    parser.add_argument('--guide', default='fixtures/guide.json')
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('check').add_argument('draft')
    commands.add_parser('receipt').add_argument('publication')
    args = parser.parse_args(argv)
    try:
        pages, publisher = open_guide(args.guide)
        result = publisher.check(pages[args.draft]) if args.action == 'check' else publisher.receipt(args.publication)
    except (OSError, KeyError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
