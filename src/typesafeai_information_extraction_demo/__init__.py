import argparse
import json
import os
import re
from itertools import permutations, product
from pathlib import Path

import spacy
from dotenv import load_dotenv
from pyvis.network import Network
from typesafe_sdk import Choice, Noul, TypeSafeClient


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Extract and visualize a schema-constrained graph")
    parser.add_argument("text")
    parser.add_argument("schema", help='e.g. "Nodes: -PERSON (human) -COLOR (color); EDGES: -LIKES"')
    parser.add_argument("-o", "--output", default="graph.html")
    args = parser.parse_args()

    halves = re.split(r"\bEDGES\s*:", args.schema, maxsplit=1, flags=re.I)
    if len(halves) != 2:
        parser.error("schema must contain EDGES:")
    parse = lambda value: dict(re.findall(r"-([A-Z][A-Z0-9_]*)\s*(?:\(([^)]*)\))?", value))
    node_types, edge_types = parse(halves[0]), parse(halves[1])
    if not node_types or not edge_types:
        parser.error("schema needs at least one -NODE and one -EDGE")

    doc = spacy.load("en_core_web_sm")(args.text)
    candidates = list(dict.fromkeys([e.text for e in doc.ents] + [t.text for t in doc if t.pos_ in {"PROPN", "NOUN", "ADJ"}]))
    client = TypeSafeClient(api_key=os.environ["API_JEV"])
    state = {"text": args.text, "schema": args.schema}
    result = client.system_one(state, {
        f"n{i}": Choice(
            instructions=f"Classify candidate {name!r} using the schema; choose NONE unless it is an entity mentioned in the text.",
            criteria={**node_types, "NONE": "Not an entity of any allowed node type."},
        ) for i, name in enumerate(candidates)
    })
    nodes = [(name, result.answers[f"n{i}"].choice) for i, name in enumerate(candidates) if result.answers[f"n{i}"].choice != "NONE"]

    possible = list(product(permutations(nodes, 2), edge_types))
    result = client.system_one(state, {
        f"e{i}": Noul(instructions=f"The text asserts as true that {a[0]!r} {edge} {b[0]!r}. Resolve references, but answer false for negated, hypothetical, or uncertain claims.")
        for i, ((a, b), edge) in enumerate(possible)
    }) if possible else None
    edges = [(a, edge, b) for i, ((a, b), edge) in enumerate(possible) if result.answers[f"e{i}"].noul >= .7]
    graph = {"nodes": [{"name": n, "type": t} for n, t in nodes], "edges": [{"source": a[0], "type": e, "target": b[0]} for a, e, b in edges]}
    print(json.dumps(graph, indent=2))

    view = Network(height="100vh", directed=True, cdn_resources="in_line")
    view.set_options('''{
      "layout": {"hierarchical": {"enabled": true, "direction": "LR", "levelSeparation": 240, "nodeSpacing": 120}},
      "physics": {"enabled": false},
      "nodes": {"font": {"size": 18}, "margin": 18},
      "edges": {"smooth": {"type": "cubicBezier"}, "font": {"size": 15, "background": "white", "strokeWidth": 6, "strokeColor": "white"}}
    }''')
    for name, label in nodes:
        view.add_node(f"{label}:{name}", label=name, title=label, group=label)
    for (source, source_label), edge, (target, target_label) in edges:
        view.add_edge(f"{source_label}:{source}", f"{target_label}:{target}", label=edge, title=edge)
    view.write_html(args.output)
    print(f"Interactive graph: {Path(args.output).resolve()}")
