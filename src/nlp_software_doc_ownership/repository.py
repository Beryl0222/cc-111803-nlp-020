import json


class JsonRepository:
    def __init__(self, path):
        self.path = path

    def read(self):
        try:
            with open(self.path, encoding='utf-8') as handle:
                value = json.load(handle)
        except FileNotFoundError:
            return []
        if not isinstance(value, list):
            raise ValueError('本地记录文件必须是列表')
        return value

    def replace(self, records):
        from pathlib import Path
        path = Path(self.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
