"""Persona digests and the e-mail rule's shared pieces (``agentprov.corpus.personas``, D-810; HL H.1.6 ``[scan]``).

Addresses are assembled at run time (``addr``): no e-mail address is written in this repository, which will be public.
"""

from __future__ import annotations

import hashlib
import time

import pytest

from agentprov.corpus import personas as p
from agentprov.corpus.spec import CorpusSpecError, parse_spec

try:  # the sealing helpers of this directory build a valid spec
    import seal_support as ss
except ImportError:  # pragma: no cover
    ss = None  # type: ignore[assignment]


def addr(local: str, domain: str) -> str:
    return "@".join((local, domain))


def found(text: str) -> list[str]:
    return [raw.decode() for _start, raw in p.find_addresses(text.encode())]


# ------------------------------------------------------------------------------------------------ matches and non-matches
@pytest.mark.parametrize(("text", "expected"), [
    (addr("ada.lovelace", "persona-one.com"), [addr("ada.lovelace", "persona-one.com")]),
    (f"<{addr('a+tag', 'sub.domain.org')}>", [addr("a+tag", "sub.domain.org")]),
    (f"mailto:{addr('x_y-z', 'host.io')}.", [addr("x_y-z", "host.io")]),  # a sentence's final dot is not the TLD's
    (f'"to": "{addr("bob", "Mixed.Case.NET")}",', [addr("bob", "Mixed.Case.NET")]),
    (f"{addr('a', 'b.com')} and {addr('c', 'd.org')}", [addr("a", "b.com"), addr("c", "d.org")]),
    (addr("a", "x.co.uk"), [addr("a", "x.co.uk")]),
    (f"a\n{addr('line', 'two.com')}", [addr("line", "two.com")]),
])
def test_addresses_are_found(text, expected):
    assert found(text) == expected


@pytest.mark.parametrize("text", [
    "pkg@1.2.3", "inspect_ai@0.3.247.dev69", "adapter@1.0.0-beta.1", "@scope/package", "@pytest.mark.slow", "name@",
    "x@localhost", "x@host", "x@.com", "x@host..com", "@@@", "a@b.c", "a@b.com1", "a@-b.com-", "user@[10.0.0.1]",
    "plain text with no at sign", "a @ b.com",
])
def test_these_are_not_addresses(text):
    assert found(text) == []


@pytest.mark.parametrize(("before", "expected_local"), [
    ("\\n", "bob"), ("\\t", "bob"), ("\\r", "bob"), ("\\b", "bob"), ("\\f", "bob"),  # a JSON escape before it
    ("\\u003c", "bob"), ("\\u00A0", "bob"),  # \\uXXXX, either case
    ("\\\\n", "bob"),  # double-escaped: a JSON string inside JSON (PROV ``apv:args``)
    ("\\x", "xbob"), ("\\a", "abob"),  # not a JSON escape letter: the local part as read
    ("n", "nbob"), ("\\\\", "bob"), ("\\\\b", "bbob"),  # no backslash; an escaped backslash, then text
])
def test_a_json_escape_before_an_address_is_not_its_local_part(before, expected_local):
    """D-810 (path-scan 6): ``\\nname@host`` is how JSON stores a newline before an address; the digest is the decoded one."""
    (raw,) = (r for _s, r in p.find_addresses((before + addr("bob", "persona-one.com")).encode()))
    assert raw == addr(expected_local, "persona-one.com").encode()


def test_an_escape_is_not_stripped_from_a_local_part_that_is_only_the_escape():
    assert found("\\n" + addr("", "persona-one.com")) == [addr("n", "persona-one.com")]  # kept as read: still a finding
    assert found("\\u0041" + addr("", "persona-one.com")) == [addr("u0041", "persona-one.com")]
    assert found("\\n" + addr("n", "persona-one.com")) == [addr("n", "persona-one.com")]


def test_a_local_part_is_at_most_64_characters_and_the_digest_is_of_what_was_read():
    long_local = "a" * 70
    (raw,) = (r for _s, r in p.find_addresses(addr(long_local, "d.com").encode()))
    assert raw == addr("a" * 64, "d.com").encode()


def test_an_address_is_found_only_inside_the_window_asked_for():
    text = (addr("first", "one.com") + " " * 50 + addr("second", "two.com")).encode()
    at_second = text.index(b"@", text.index(b"@") + 1)
    assert [r for _s, r in p.find_addresses(text, at_second)] == [addr("second", "two.com").encode()]
    assert [r for _s, r in p.find_addresses(text, 0, at_second)] == [addr("first", "one.com").encode()]


# ------------------------------------------------------------------------------------------------ linear time
@pytest.mark.parametrize("hostile", [
    b"a@" + b"a." * 500_000,
    b"a@" + b"a" * 1_000_000,
    b"@" * 1_000_000,
    b"a@a" * 400_000,
    b"x@" + b"a-" * 500_000,
    b"a@" + b"a." * 300_000 + b"!",
    (b"a@" + b"b" * 60 + b".") * 20_000,
    b"." * 1_000_000 + b"@a.b",
    b"a" * 1_000_000 + b"@a.bc",
], ids=range(9))
def test_hostile_input_is_matched_in_linear_time(hostile):
    start = time.perf_counter()
    p.find_addresses(hostile)
    assert time.perf_counter() - start < 3.0  # a quadratic search over these inputs takes minutes


def test_time_grows_linearly_with_the_input():
    def cost(n: int) -> float:
        data = b"a@" + b"a." * n
        t = time.perf_counter()
        p.find_addresses(data)
        return time.perf_counter() - t

    small, large = cost(100_000), cost(800_000)
    assert large < max(small, 0.005) * 40  # eight times the input, far from sixty-four times the time


# ------------------------------------------------------------------------------------------------ normalisation and digests
def test_the_digest_is_of_the_ascii_lower_cased_address_and_nothing_else():
    a = addr("Ada.Lovelace+Tag", "Persona-One.COM")
    expected = "sha256:" + hashlib.sha256(a.lower().encode()).hexdigest()
    assert p.address_digest(a.encode()) == expected == p.address_digest(a.lower().encode())
    assert p.address_digest(addr("a+b", "x.com").encode()) != p.address_digest(addr("a", "x.com").encode())  # +tags count
    assert p.normalise_address(a.encode()) == a.lower()


@pytest.mark.parametrize(("domain", "klass"), [
    ("example.com", "reserved"), ("EXAMPLE.ORG", "reserved"), ("example.net", "reserved"), ("mail.example", "reserved"),
    ("host.test", "reserved"), ("x.invalid", "reserved"), ("db.localhost", "reserved"),
    ("test.com", "other"), ("example.co", "other"), ("sub.example.com", "other"), ("myexample.com", "other"),
    ("testing.org", "other"), ("invalid.com", "other"),
    ("gmail.com", "public-freemail"), ("Outlook.com", "public-freemail"), ("protonmail.com", "public-freemail"),
    ("bluesparrowtech.com", "other"),
])
def test_domain_classes(domain, klass):
    assert p.domain_class(domain) == klass


def test_a_reserved_name_is_exactly_the_rfc_2606_6761_set():
    assert p.is_reserved_domain("example.com") and p.is_reserved_domain("a.b.example")
    assert not p.is_reserved_domain("test.com") and not p.is_reserved_domain("example.com.au")


# ------------------------------------------------------------------------------------------------ persona files
def persona_text(digests: list[str], **group) -> str:
    fields = {"source_id": "bench", "repo": "https://example.org/owner/repo", "commit": "a" * 40, "file": "src/data.py", **group}
    body = "\n".join(f"{k} = {v!r}".replace("'", '"') for k, v in fields.items() if v is not None)
    listing = ", ".join(f'"{d}"' for d in digests)
    return f'format = "agentprov-personas/0.1"\nid = "bench-one"\n[[group]]\n{body}\naddresses = [{listing}]\n'


GOOD = [p.address_digest(addr(n, "x.com").encode()) for n in ("a", "b", "c")]


def test_a_valid_persona_file_parses_to_its_digest_union():
    doc = p.parse_persona_file(persona_text(sorted(GOOD)).encode())
    assert doc.id == "bench-one" and doc.digests == frozenset(GOOD) and len(doc.groups) == 1
    assert doc.by_class["upstream-data"] == frozenset(GOOD) and not doc.by_class["model-generated"]
    two = persona_text(sorted(GOOD)) + persona_text(sorted(GOOD)[:1], file="src/other.py").split("\n", 2)[2]
    assert p.persona_digests([persona_text(sorted(GOOD)).encode(), two.encode()])["upstream-data"] == frozenset(GOOD)


@pytest.mark.parametrize(("mutate", "why"), [
    (lambda: persona_text(GOOD[::-1] if GOOD != sorted(GOOD) else GOOD + GOOD[:1]), "sorted and unique"),
    (lambda: persona_text([addr("a", "x.com")]), "digests"),  # an address instead of a digest is refused
    (lambda: persona_text(["sha256:" + "G" * 64]), "digests"),
    (lambda: persona_text([]), "digests"),
    (lambda: persona_text(sorted(GOOD), commit="abc"), "commit"),
    (lambda: persona_text(sorted(GOOD), commit=None), "commit"),
    (lambda: persona_text(sorted(GOOD), doi="10.5281/zenodo.1"), "pins the evidence"),
    (lambda: persona_text(sorted(GOOD), repo="http://plain.example/x"), "https"),
    (lambda: persona_text(sorted(GOOD), extra="1"), "unknown key"),
    (lambda: persona_text(sorted(GOOD)).replace("agentprov-personas/0.1", "agentprov-personas/9"), "format"),
    (lambda: persona_text(sorted(GOOD)).replace('id = "bench-one"\n', ""), "missing"),
    (lambda: "not toml [", "TOML"),
])
def test_a_malformed_persona_file_is_refused(mutate, why):
    with pytest.raises(p.PersonaError, match=why):
        p.parse_persona_file(mutate().encode())


def test_persona_errors_never_quote_the_files_values():
    canary = addr("canary.person", "persona-canary.com")
    for text in (persona_text([canary]), persona_text(sorted(GOOD)).replace("src/data.py", canary) + canary):
        try:
            p.parse_persona_file(text.encode())
        except p.PersonaError as exc:
            assert canary not in str(exc) and "persona-canary" not in str(exc)


def test_a_file_name_group_is_a_separate_class():
    other = [p.address_digest(addr("icon", "2x.png").encode())]
    text = persona_text(sorted(GOOD)) + persona_text(other, file="runs/x.json", **{"class": "file-name"}).split("\n", 2)[2]
    parsed = p.parse_persona_file(text.encode())
    assert parsed.digests == frozenset(GOOD) and parsed.file_names == frozenset(other)
    union = p.persona_digests([text.encode()])
    assert union["upstream-data"] == frozenset(GOOD) and union["file-name"] == frozenset(other)


def test_the_class_is_closed_and_a_digest_has_one_class():
    with pytest.raises(p.PersonaError, match="class"):
        p.parse_persona_file(persona_text(sorted(GOOD), **{"class": "benign"}).encode())
    both = persona_text(sorted(GOOD)) + persona_text(sorted(GOOD)[:1], file="b.py", **{"class": "file-name"}).split("\n", 2)[2]
    with pytest.raises(p.PersonaError, match="two classes"):
        p.parse_persona_file(both.encode())
    one = persona_text(sorted(GOOD)).encode()
    two = persona_text(sorted(GOOD)[:1], **{"class": "file-name"}).encode()
    with pytest.raises(p.PersonaError):
        p.persona_digests([one, two])


def observed_text(klass: str, rows: list[tuple[str, dict]]) -> str:
    entries = ", ".join("{ " + ", ".join(f'{k} = "{v}"' for k, v in {"address": d, "ex": "ex_" + "a" * 26, "record": "m3",
                                                                    "pointer": "/parts/0/text", "actor_kind": "llm_agent",
                                                                    **extra}.items()) + " }" for d, extra in rows)
    return (f'format = "agentprov-personas/0.1"\nid = "obs"\n[[group]]\nclass = "{klass}"\nsource_id = "bench"\n'
            f'repo = "https://example.org/owner/repo"\ncommit = "{"a" * 40}"\ncorpus_id = "mini"\nentries = [{entries}]\n')


@pytest.mark.parametrize("klass", ["benchmark-input", "model-generated"])
def test_an_observed_group_holds_one_aer_location_per_address(klass):
    rows = [(d, {}) for d in sorted(GOOD)]
    parsed = p.parse_persona_file(observed_text(klass, rows).encode())
    assert parsed.by_class[klass] == frozenset(GOOD) and parsed.digests == frozenset()


@pytest.mark.parametrize(("extra", "why"), [({"ex": "x1"}, "evidence"), ({"record": "bad record"}, "evidence"),
                                            ({"pointer": "parts"}, "evidence"), ({"pointer": "/" + "a" * 301}, "evidence"),
                                            ({"actor_kind": "LLM"}, "evidence"), ({"address": addr("a", "b.com")}, "evidence")])
def test_an_observed_entry_needs_its_evidence_and_never_an_address(extra, why):
    rows = [(sorted(GOOD)[0], extra)]
    with pytest.raises(p.PersonaError, match=why):
        p.parse_persona_file(observed_text("model-generated", rows).encode())


def test_observed_entries_are_sorted_and_unique_and_a_group_has_the_keys_of_its_class():
    d = sorted(GOOD)
    with pytest.raises(p.PersonaError, match="sorted"):
        p.parse_persona_file(observed_text("model-generated", [(d[1], {}), (d[0], {})]).encode())
    with pytest.raises(p.PersonaError, match="sorted"):
        p.parse_persona_file(observed_text("model-generated", [(d[0], {}), (d[0], {})]).encode())
    with pytest.raises(p.PersonaError, match="missing"):  # an observed group has no ``file`` and needs ``corpus_id``
        p.parse_persona_file(observed_text("model-generated", [(d[0], {})]).replace('corpus_id = "mini"\n', "").encode())
    with pytest.raises(p.PersonaError, match="unknown key"):
        p.parse_persona_file((persona_text(d) + 'entries = []\n').encode())


def object_text(rows: list[tuple[str, str]], corpus_id: str = "mini") -> str:
    entries = ", ".join(f'{{ address = "{d}", object = "{o}" }}' for d, o in rows)
    return (f'format = "agentprov-personas/0.1"\nid = "obj"\n[[group]]\nclass = "withhold-object"\nsource_id = "bench"\n'
            f'repo = "https://example.org/owner/repo"\ncommit = "{"a" * 40}"\ncorpus_id = "{corpus_id}"\nentries = [{entries}]\n')


def test_a_withhold_object_group_holds_the_raw_object_of_each_address():
    obj = "sha256:" + "b" * 64
    parsed = p.parse_persona_file(object_text([(d, obj) for d in sorted(GOOD)]).encode())
    assert parsed.by_class["withhold-object"] == frozenset(GOOD) and "withhold-object" in p.CORPUS_CLASSES
    assert set(p.WITHHOLD_CLASSES) == {"withhold", "withhold-object"}
    with pytest.raises(p.PersonaError, match="object are sha256"):
        p.parse_persona_file(object_text([(sorted(GOOD)[0], "b" * 64)]).encode())  # the object as a label
    with pytest.raises(p.PersonaError, match="object are sha256"):
        p.parse_persona_file(object_text([(addr("a", "b.com"), obj)]).encode())  # never an address
    with pytest.raises(p.PersonaError, match="unknown key"):  # no AER evidence: there is none for such an address
        p.parse_persona_file(object_text([(sorted(GOOD)[0], obj)]).replace(" }", ', ex = "ex_' + "a" * 26 + '" }').encode())
    with pytest.raises(p.PersonaError, match="missing"):
        p.parse_persona_file(object_text([(sorted(GOOD)[0], obj)]).replace('corpus_id = "mini"\n', "").encode())


def test_a_digest_in_an_observed_and_an_upstream_group_is_refused():
    d = sorted(GOOD)
    text = persona_text(d) + observed_text("model-generated", [(d[0], {})]).split("\n", 2)[2]
    with pytest.raises(p.PersonaError, match="two classes"):
        p.parse_persona_file(text.encode())


def test_a_doi_pinned_group_is_valid():
    text = persona_text(sorted(GOOD), repo=None, commit=None, doi="10.5281/zenodo.12528189")
    assert p.parse_persona_file(text.encode()).digests == frozenset(GOOD)


# ------------------------------------------------------------------------------------------------ the spec's [scan] table
def spec_with(scan: str) -> bytes:
    assert ss is not None
    return (ss.SPEC + scan).encode()


REF = f'{{ path = "../personas/bench.personas.toml", sha256 = "sha256:{"0" * 64}" }}'


def test_a_spec_without_scan_clears_no_persona():
    assert parse_spec(spec_with("")).persona_files == ()


def test_a_spec_names_its_persona_files_by_path_and_digest():
    spec = parse_spec(spec_with(f"\n[scan]\npersonas = [{REF}]\n"))
    assert spec.persona_files == (("../personas/bench.personas.toml", "sha256:" + "0" * 64),)


@pytest.mark.parametrize("scan", [
    "[scan]\n", "[scan]\npersonas = []\n", "[scan]\npersonas = 3\n", "[scan]\npersonas = [{ path = 'a.personas.toml' }]\n",
    f"[scan]\npersonas = [{REF}]\nextra = 1\n",
    f'[scan]\npersonas = [{{ path = "../../x.personas.toml", sha256 = "sha256:{"0" * 64}" }}]\n',
    f'[scan]\npersonas = [{{ path = "/abs/x.personas.toml", sha256 = "sha256:{"0" * 64}" }}]\n',
    f'[scan]\npersonas = [{{ path = "x.toml", sha256 = "sha256:{"0" * 64}" }}]\n',
    f'[scan]\npersonas = [{{ path = "x.personas.toml", sha256 = "sha256:{"0" * 63}" }}]\n',
    f'[scan]\npersonas = [{{ path = "a/x.personas.toml", sha256 = "sha256:{"0" * 64}" }}, '
    f'{{ path = "b/x.personas.toml", sha256 = "sha256:{"1" * 64}" }}]\n',
    '[scan]\npersonas = [{ path = "x.personas.toml", sha256 = "sha256:' + "0" * 64 + '", addresses = ["a"] }]\n',
])
def test_a_malformed_scan_table_is_refused(scan):
    with pytest.raises(CorpusSpecError):
        parse_spec(spec_with("\n" + scan))
