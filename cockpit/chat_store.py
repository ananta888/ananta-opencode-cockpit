"""Atomic, process-safe managed chat metadata."""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TypedDict


class ChatRecord(TypedDict):
    id: str
    title: str
    project: str
    parent_id: str
    session_id: str
    pane: str
    holding_session: str
    host_session: str
    host_main: str
    socket: str
    model: str
    mcp: bool
    status: str
    placement: str
    kind: str
    error: str


class ChatStoreError(RuntimeError):
    """State cannot be read or updated safely."""


class ChatStore:
    def __init__(self) -> None:
        self.directory = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state') / 'ananta-cockpit'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'chats.json'

    @contextmanager
    def lock(self, name: str = 'store') -> Iterator[None]:
        if not name.replace('-', '').replace('_', '').isalnum():
            raise ChatStoreError('Invalid lock identifier')
        with (self.directory / f'{name}.lock').open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield

    def _read(self) -> list[ChatRecord]:
        if not self.path.exists():
            return []
        try:
            records = json.loads(self.path.read_text())
        except (OSError, ValueError) as error:
            raise ChatStoreError(f'Cannot read {self.path}: {error}') from error
        if not isinstance(records, list) or any(not isinstance(row, dict) or not isinstance(row.get('id'), str) for row in records):
            raise ChatStoreError(f'Invalid chat records in {self.path}')
        return records

    def list(self) -> list[ChatRecord]:
        with self.lock():
            return self._read()

    def get(self, chat_id: str) -> ChatRecord:
        for record in self.list():
            if record['id'] == chat_id:
                return record
        raise ChatStoreError(f'Unknown chat: {chat_id}')

    def save(self, record: ChatRecord) -> ChatRecord:
        return self.update(record['id'], record)

    def update(self, chat_id: str, changes: dict[str, str | bool]) -> ChatRecord:
        with self.lock():
            records = self._read()
            record = next((row for row in records if row['id'] == chat_id), None)
            if record is None:
                record = dict(changes)
                records.append(record)
            else:
                record.update(changes)
            with tempfile.NamedTemporaryFile(mode='w', dir=self.directory, delete=False) as handle:
                temporary = Path(handle.name)
                try:
                    json.dump(records, handle, indent=2)
                    handle.write('\n')
                    handle.flush()
                    os.fsync(handle.fileno())
                except (OSError, TypeError):
                    temporary.unlink(missing_ok=True)
                    raise
            os.replace(temporary, self.path)
            return record
