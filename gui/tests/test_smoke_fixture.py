from pathlib import Path


def test_mini_corpus_builds(mini_corpus: Path) -> None:
    assert (mini_corpus.with_name("mini.partial") / "executions.jsonl").is_file()
