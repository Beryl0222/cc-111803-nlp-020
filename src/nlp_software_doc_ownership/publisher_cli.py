import argparse
import json
from pathlib import Path

from .contracts import ContractRegistry, Endpoint
from .editions import DocPublisher, Page
from .examples import Call, ExampleCheck
from .review import build_reviewer


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


def load_review_inputs(guide_path, records_path, business_path):
    guide_data = json.loads(Path(guide_path).read_text(encoding='utf-8'))
    records = json.loads(Path(records_path).read_text(encoding='utf-8'))
    business = json.loads(Path(business_path).read_text(encoding='utf-8'))
    # 业务目录用 version 键登记弃用状态，审校器统一转换为 edition
    guide_data.setdefault('deprecations', []).extend(
        {'product': row['product'], 'edition': row['version'],
         'path': row['path'], 'status': row['status']}
        for row in business.get('endpoints', ())
    )
    guide_data.setdefault('sections', []).extend(
        {'product': 'Mercury', 'edition': row['version'], 'anchor': row['anchor']}
        for row in business.get('sections', ())
    )
    return guide_data, records


def main(argv=None):
    parser = argparse.ArgumentParser(description='接口文档核批')
    parser.add_argument('--guide', default='fixtures/guide.json')
    parser.add_argument('--records', default='fixtures/records.json')
    parser.add_argument('--business', default='fixtures/business.json')
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('check').add_argument('draft')
    commands.add_parser('receipt').add_argument('publication')
    review = commands.add_parser('review')
    review.add_argument('product')
    review.add_argument('edition')
    review_page = commands.add_parser('review-page')
    review_page.add_argument('draft')
    args = parser.parse_args(argv)
    try:
        pages, publisher = open_guide(args.guide)
        if args.action in ('review', 'review-page'):
            guide_data, records = load_review_inputs(
                args.guide, args.records, args.business)
            registry = ContractRegistry(
                Endpoint(**row) for row in guide_data['endpoints'])
            reviewer = build_reviewer(guide_data, records, registry, pages, publisher)
            if args.action == 'review':
                result = reviewer.review_edition(args.product, args.edition)
            else:
                result = reviewer.review_page(pages[args.draft])
        elif args.action == 'check':
            result = publisher.check(pages[args.draft])
        else:
            result = publisher.receipt(args.publication)
    except (OSError, KeyError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
