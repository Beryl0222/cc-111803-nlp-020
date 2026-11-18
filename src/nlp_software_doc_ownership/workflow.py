from .records import TextRecord
from .text import normalize_text, tokens


class TextWorkflow:
    def __init__(self, repository):
        self.repository = repository

    def ingest(self, values):
        if not isinstance(values, list):
            raise TypeError('导入内容必须是记录列表')
        records = []
        for value in values:
            record = TextRecord.from_dict(value)
            normalized = normalize_text(record.text)
            records.append({**record.to_dict(), 'text': normalized, 'tokens': tokens(normalized)})
        self.repository.replace(records)
        return {'received': len(records), 'stored': len(records)}

    def list_records(self, source=None):
        records = self.repository.read()
        if source is not None:
            records = [record for record in records if record['source'] == source]
        return records
