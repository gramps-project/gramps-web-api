#! /usr/bin/env python3

"""Benchmark the full-text search index on synthetic trees.

The searched tree has about 110k objects with deliberately common names
("john" for 20% of the people, "smith" for 11%). Further, smaller trees can
be added to the same database to measure a multi-tree installation.

Example:

    python scripts/search_benchmark.py sqlite:////tmp/search.db
    python scripts/search_benchmark.py postgresql://user:pw@host/db --trees 10
"""

import argparse
import random
import statistics
import time
import uuid

from gramps_webapi.api.search.indexer import SearchIndexer
from gramps_webapi.api.search.text import ObjectRows, tokenize

TOP_SURNAMES = [
    "smith", "miller", "schmidt", "garcia", "johnson", "meyer", "brown",
    "weber", "jones", "wagner", "davis", "becker", "wilson", "fischer",
]  # fmt: skip
TOP_GIVEN = [
    "john", "mary", "william", "elizabeth", "james", "anna", "george",
    "margaret", "thomas", "sarah", "johann", "maria", "charles", "catherine",
]  # fmt: skip
SYLLABLES = (
    "ba ber co dal den el fa gor han is kel lo man mor na ol per ra rin sa sel"
    " ta ton ul vik wal zen ke tri bo nus ard"
).split()
WORDS = (
    "the of and in to was he she his her at born lived farmer married church"
    " parish record moved city county son daughter year died buried family"
    " letter census emigrated village worked mill house land will estate"
).split()

QUERIES = [
    "zzrare",
    "smith",
    "john",
    "john smith",
    '"john smith"',
    "marriage smith",
    "birth john smith",
    "smi*",
    "j*",
    "smith OR miller",
    "i00003000",
    "*",
]


def _words(rng, n, exclude):
    out, seen = [], set(exclude)
    while len(out) < n:
        word = "".join(rng.choice(SYLLABLES) for _ in range(rng.randint(2, 3)))
        if word not in seen:
            seen.add(word)
            out.append(word)
    return out


def generate(seed: int, people: int):
    """Yield the index rows of a synthetic tree."""
    rng = random.Random(seed)
    scale = people / 35000
    surnames = TOP_SURNAMES + _words(rng, max(50, int(5000 * scale)), TOP_SURNAMES)
    given = TOP_GIVEN + _words(rng, 400, TOP_GIVEN + surnames)
    surname_weights = [1 / (r + 1) for r in range(len(surnames))]
    given_weights = [1 / (r + 1) ** 1.1 for r in range(len(given))]
    counter = iter(range(10**9))

    def rows(obj_type, text, private_rate, **kwargs):
        n = next(counter)
        private = rng.random() < private_rate
        content = " ".join(tokenize(f"i{n:08d} {text}"))
        docs = [("own", "full" if private else "all", private, content)]
        return ObjectRows(f"h{n:08d}", obj_type, private, 1.6e9 + n, docs, **kwargs)

    person_handles = []
    for _ in range(people):
        name = (
            rng.choices(given, given_weights)[0]
            + " "
            + rng.choices(surnames, surname_weights)[0]
        )
        events = []
        for etype, rate in (("birth", 0.8), ("death", 0.35), ("burial", 0.12)):
            if rng.random() < rate:
                event = rows("event", etype, 0.03)
                events.append((event.handle, "participant", rng.random() < 0.02))
                yield event
        person = rows("person", name, 0.05, refs=events)
        person.docs.append(("name", "all", rng.random() < 0.03, name))
        person_handles.append(person.handle)
        yield person
    for _ in range(int(13000 * scale)):
        refs = [(h, "parent", False) for h in rng.sample(person_handles, 2)]
        if rng.random() < 0.7:
            event = rows("event", "marriage", 0.03)
            refs.append((event.handle, "participant", rng.random() < 0.02))
            yield event
        yield rows("family", "married", 0.03, refs=refs)
    for _ in range(int(9000 * scale)):
        text = " ".join(rng.choice(WORDS) for _ in range(rng.randint(3, 40)))
        yield rows(rng.choice(["note", "place", "citation", "source"]), text, 0.05)


def build(db_url: str, tree: str, seed: int, people: int) -> SearchIndexer:
    indexer = SearchIndexer(tree=tree, db_url=db_url)
    indexer._add_objects_chunked(generate(seed, people), chunk_size=5000)
    indexer.analyze()
    if indexer.dialect == "postgresql":
        # as autovacuum does shortly after large changes
        with indexer.engine.connect() as conn:
            conn.exec_driver_sql("ANALYZE search_doc, search_obj, search_ref")
            conn.commit()
    return indexer


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("db_url", help="search index database URL")
    parser.add_argument("--trees", type=int, default=1, help="number of trees")
    parser.add_argument("--repeat", type=int, default=5)
    args = parser.parse_args()

    run = uuid.uuid4().hex[:8]
    rng = random.Random(42)
    t0 = time.time()
    indexer = build(args.db_url, f"bench-{run}-0", 0, 35000)
    others = [
        build(
            args.db_url,
            f"bench-{run}-{i}",
            i,
            max(50, min(35000, int(rng.lognormvariate(7.3, 1.2)))),
        )
        for i in range(1, args.trees)
    ]
    objects = indexer.count(include_private=True)
    print(f"built {args.trees} tree(s) in {time.time() - t0:.0f}s;")
    print(f"searching a tree of {objects} objects; page 1, median of {args.repeat}")
    print(f"{'query':22}{'guest':>10}{'owner':>10}{'hits':>10}")
    try:
        for query in QUERIES:
            times = {}
            for guest in (True, False):
                indexer.search(query, 1, 20, include_private=not guest)
                samples = []
                for _ in range(args.repeat):
                    t0 = time.perf_counter()
                    total, _ = indexer.search(query, 1, 20, include_private=not guest)
                    samples.append(time.perf_counter() - t0)
                times[guest] = (statistics.median(samples) * 1000, total)
            print(
                f"{query:22}{times[True][0]:>8.1f}ms{times[False][0]:>8.1f}ms"
                f"{times[True][1]:>10}"
            )
    finally:
        for tree_indexer in [indexer, *others]:
            tree_indexer._delete_all()


if __name__ == "__main__":
    main()
