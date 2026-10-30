"""K.11.1 F-1 / F-5 for the tier-1 parsers: success or an IngestError with a G.3.9 code, deterministic, nothing written."""

from __future__ import annotations

import io
import json
import warnings
import zipfile

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agentprov.errors import INGEST_CODES, IngestError
from agentprov.ingest.archives import iter_zip_members, open_archive
from agentprov.ingest.loaders import iter_jsonl, strict_json_loads
from agentprov.ingest.names import logical_name
from agentprov.ingest.quote import escape_untrusted, quote_untrusted
from agentprov.ingest.yamlsafe import YAMLError, safe_load

SEED_ZIP = io.BytesIO()
with zipfile.ZipFile(SEED_ZIP, "w") as _z:
    _z.writestr("a.json", b'{"a": 1}' * 20)
    _z.writestr("dir/b.jsonl", b"[1]\n" * 50)
SEED = SEED_ZIP.getvalue()
SEED_JSON = json.dumps({"a": [1, 2.5, "x", None, {"b": True}], "c": chr(0xE9)}).encode()

FUZZ = settings(max_examples=250, deadline=2000, suppress_health_check=[HealthCheck.too_slow])


def mutate(seed: bytes):
    def apply(ops: list[tuple[str, int, int]]) -> bytes:
        data = bytearray(seed)
        for op, pos, val in ops:
            if not data:
                break
            i = pos % len(data)
            if op == "flip":
                data[i] ^= (val % 255) + 1
            elif op == "cut":
                del data[i:]
            elif op == "ins":
                data[i:i] = bytes([val % 256])
            elif op == "del":
                del data[i : i + 1 + val % 8]
        return bytes(data)

    return st.lists(st.tuples(st.sampled_from(["flip", "cut", "ins", "del"]), st.integers(0, 10**6), st.integers(0, 10**6)), max_size=6).map(apply)


def outcome(fn):
    try:
        return ("ok", fn())
    except IngestError as exc:
        assert exc.code in INGEST_CODES
        return ("err", exc.code)


@FUZZ
@given(mutate(SEED_JSON))
def test_f1_mutated_json(data):
    first = outcome(lambda: strict_json_loads(data))
    assert first == outcome(lambda: strict_json_loads(data))


@FUZZ
@given(st.lists(mutate(SEED_JSON), max_size=4))
def test_f1_mutated_jsonl(lines):
    data = b"\n".join(lines)

    def run():
        issues = []
        rows = list(iter_jsonl(io.BytesIO(data), issues=issues))
        return rows, [(i.code, i.line, i.offset) for i in issues]

    first = run()
    assert first == run()
    assert all(code in INGEST_CODES for code, _, _ in first[1])


@FUZZ
@given(mutate(SEED))
def test_f1_mutated_zip_never_raises_an_untyped_exception(data):
    def run():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            archive = open_archive(io.BytesIO(data), release=False)
            try:
                result = []
                for member in iter_zip_members(archive):
                    result.append((member.label, member.disposition, member.code))
                    if member.disposition == "selected":
                        try:
                            result.append(len(b"".join(member.iter_chunks())))
                        except IngestError as exc:
                            assert exc.code in INGEST_CODES
                            result.append(exc.code)
                return result
            finally:
                archive.close()

    first = outcome(run)
    assert first == outcome(run)


@FUZZ
@given(st.binary(max_size=2000))
def test_f1_random_bytes_as_archives(data):
    outcome(lambda: open_archive(io.BytesIO(data), release=False).close())


@FUZZ
@given(st.text(max_size=300))
def test_f1_names_are_valid_or_typed_errors(name):
    result = outcome(lambda: logical_name(name))
    if result[0] == "ok":
        assert result[1] and "\\" not in result[1] and not result[1].startswith("/") and ".." not in result[1].split("/")
    else:
        assert result[1] in {"ingest.name.invalid", "ingest.archive.traversal"}


@FUZZ
@given(st.text(max_size=300))
def test_f1_display_helpers_are_total(text):
    assert escape_untrusted(text) is not None
    assert quote_untrusted(text, text[:20]).count("\n") >= 2


@FUZZ
@given(st.text(max_size=300))
def test_f1_yaml_gives_a_value_or_a_typed_failure(text):
    try:
        safe_load(text)
    except (IngestError, YAMLError):
        pass
