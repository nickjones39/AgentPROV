"""D-500/D-501: the corpus manifest's ``ontology.version`` is the vocabulary version the PROV documents state.

``apv:vocabularyVersion`` comes from ``prov.vocab.VOCAB_VERSION`` (0.2.0 since regen items 85/86). By user decision
(2026-10-14), apv 0.2.0 rides with ``agentprov-corpus/0.2`` (deferrals part C), so the value is per format
(``corpus.manifest.ONTOLOGY_VERSIONS``): the written format records the vocabulary the PROV documents state, and the
frozen ``agentprov-corpus/0.1`` keeps 0.1.0 (D-163).
"""

from __future__ import annotations

from agentprov.corpus.manifest import FORMAT, ONTOLOGY_VERSIONS, corpus_schema
from agentprov.prov.vocab import VOCAB_VERSION


def test_the_written_corpus_format_records_the_vocabulary_version() -> None:
    assert FORMAT == "agentprov-corpus/0.2"
    assert corpus_schema()["properties"]["ontology"]["properties"]["version"]["const"] == VOCAB_VERSION
    assert ONTOLOGY_VERSIONS[FORMAT] == VOCAB_VERSION


def test_the_frozen_format_keeps_its_own_version() -> None:
    assert corpus_schema("agentprov-corpus/0.1")["properties"]["ontology"]["properties"]["version"]["const"] == "0.1.0"
    assert ONTOLOGY_VERSIONS["agentprov-corpus/0.1"] == "0.1.0"
