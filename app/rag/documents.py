"""Persistent bounded PDF staging. Only server-derived opaque references are paths.

The directory is operator-controlled and must not be writable by customers.
"""
import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path

from app.jobs.models import JobScope
from app.parsers.pdf import MAX_BYTES


class StorageQuotaExceeded(Exception):
    """Tenant retained document capacity reached; operator retention is required."""


class DocumentError(ValueError):
    pass


def document_reference(scope: JobScope, digest: str, pipeline: str) -> str:
    identity = json.dumps([scope.values, digest, pipeline], separators=(',', ':'))
    return hashlib.sha256(identity.encode()).hexdigest()


class RagDocumentStore:
    def __init__(self, directory: Path, *, max_tenant_documents=1000):
        if type(max_tenant_documents) is not int or not 1 <= max_tenant_documents <= 1000000:
            raise DocumentError('Invalid tenant document limit.')
        self.max_tenant_documents = max_tenant_documents
        directory = Path(directory).absolute()
        # Reject symlink/reparse-point components before resolving the root.
        for part in (directory, *directory.parents):
            if part.is_symlink() or part.is_junction():
                raise DocumentError('Unsafe document directory.')
        directory.mkdir(parents=True, exist_ok=True)
        self.directory = directory.resolve(strict=True)

    def _path(self, reference):
        if self.directory.is_symlink() or self.directory.is_junction() or self.directory.resolve() != self.directory:
            raise DocumentError('Unsafe document directory.')
        if type(reference) is not str or not re.fullmatch(r'[0-9a-f]{64}', reference):
            raise DocumentError('Invalid document reference.')
        path = self.directory / (reference + '.pdf')
        if path.is_symlink() or path.is_junction() or path.resolve().parent != self.directory:
            raise DocumentError('Unsafe document reference.')
        return path

    def read(self, reference):
        path = self._path(reference)
        try:
            # O_NOFOLLOW on POSIX; trusted directory + lstat/fstat validation on Windows.
            before = path.lstat()
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
                raise DocumentError('Invalid staged PDF.')
            descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
            with os.fdopen(descriptor, 'rb') as handle:
                after = os.fstat(handle.fileno())
                if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                    raise DocumentError('Invalid staged PDF.')
                data = handle.read(MAX_BYTES + 1)
            if not data or len(data) > MAX_BYTES:
                raise DocumentError('Invalid staged PDF.')
            return data
        except OSError:
            raise DocumentError('Staged PDF unavailable.') from None

    @staticmethod
    def identity(data, scope, pipeline):
        if type(data) is not bytes or not data or len(data) > MAX_BYTES or b'%PDF-' not in data[:1024]:
            raise DocumentError('Invalid or oversized PDF.')
        digest = hashlib.sha256(data).hexdigest()
        reference = document_reference(scope, digest, pipeline)
        return reference, digest

    def stage(self, data: bytes, scope: JobScope, pipeline: str):
        reference, digest = self.identity(data, scope, pipeline)
        path = self._path(reference)
        if path.exists():
            if hashlib.sha256(self.read(reference)).hexdigest() != digest:
                raise DocumentError('Staged PDF integrity failure.')
            return reference, digest
        descriptor, temporary = tempfile.mkstemp(prefix='.stage-', dir=self.directory)
        try:
            with os.fdopen(descriptor, 'wb') as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            self._path(reference)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return reference, digest

    def delete(self, reference):
        # Explicit single file only. Never recursively delete; operators own retention.
        path = self._path(reference)
        if path.exists():
            path.unlink()
