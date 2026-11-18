from dataclasses import dataclass


@dataclass(frozen=True)
class TextRecord:
    record_id: str
    source: str
    revision: int
    text: str

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            raise TypeError('每条记录必须是对象')
        record = cls(value.get('record_id'), value.get('source'), value.get('revision'), value.get('text'))
        if not record.record_id or not record.source or not isinstance(record.revision, int) or record.revision < 1:
            raise ValueError('记录标识、来源和正整数修订号为必填项')
        if not isinstance(record.text, str):
            raise TypeError('记录文本必须是字符串')
        return record

    def to_dict(self):
        return {'record_id': self.record_id, 'source': self.source, 'revision': self.revision, 'text': self.text}
