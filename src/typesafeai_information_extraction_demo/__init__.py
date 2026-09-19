import argparse
import json
import os
import re
from itertools import product
from pathlib import Path

import spacy
from dotenv import load_dotenv
from pyvis.network import Network
from typesafe_sdk import Choice, Noul, TypeSafeClient

type Node = tuple[str, str, int]
type Edge = tuple[Node, str, Node]


def parse_schema(schema: str) -> tuple[dict[str, str], list[tuple[str, str, str]]]:
    """Parse node descriptions and typed edge definitions from the schema."""
    halves = re.split(r"\bEDGES\s*:", schema, maxsplit=1, flags=re.I)
    if len(halves) != 2:
        raise ValueError("schema must contain EDGES:")
    nodes = dict(re.findall(r"-([A-Z][A-Z0-9_]*)\s*(?:\(([^)]*)\))?", halves[0]))
    edges = re.findall(r"-([A-Z][A-Z0-9_]*)\s*\(\s*([A-Z][A-Z0-9_]*)\s*->\s*([A-Z][A-Z0-9_]*)\s*\)", halves[1])
    if not nodes or not edges or any(a not in nodes or b not in nodes for _, a, b in edges):
        raise ValueError("schema needs -NODE (description) and -EDGE (SOURCE_NODE -> TARGET_NODE) definitions")
    return nodes, edges


def run_spacy_ner(text: str) -> list[tuple[str, int]]:
    """Use spaCy to propose unique entities with zero-based token indices."""
    doc = spacy.load("en_core_web_sm")(text)
    found = {}
    for name, index in [(e.text, e.start) for e in doc.ents] + [(t.text, t.i) for t in doc if t.pos_ in {"PROPN", "NOUN", "ADJ"}]:
        found.setdefault(name, index)
    return list(found.items())


def validate_entities(client: TypeSafeClient, state: dict[str, str], types: dict[str, str], candidates: list[tuple[str, int]]) -> list[Node]:
    """Use TypeSafe AI to retain and type valid entity candidates."""
    result = client.system_one(state, {f"n{i}": Choice(instructions=f"Classify candidate {name!r} using the schema; choose NONE unless it is an entity mentioned in the text.", criteria={**types, "NONE": "Not an entity of any allowed node type."}) for i, (name, _) in enumerate(candidates)})
    return [(name, result.answers[f"n{i}"].choice, index) for i, (name, index) in enumerate(candidates) if result.answers[f"n{i}"].choice != "NONE"]


def detect_edges(client: TypeSafeClient, state: dict[str, str], nodes: list[Node], types: list[tuple[str, str, str]], max_distance: int) -> list[Edge]:
    """Use TypeSafe AI to detect edges between type-compatible nodes."""
    possible = [(a, edge, b) for edge, source, target in types for a, b in product(nodes, repeat=2) if a[1] == source and b[1] == target and a != b and abs(a[2] - b[2]) <= max_distance]
    result = client.system_one(state, {f"e{i}": Noul(instructions=f"The text asserts as true that {a[0]!r} {edge} {b[0]!r}. Resolve references, but answer false for negated, hypothetical, or uncertain claims.") for i, (a, edge, b) in enumerate(possible)}) if possible else None
    return [(a, edge, b) for i, (a, edge, b) in enumerate(possible) if result.answers[f"e{i}"].noul >= .7]


def visualize_graph(nodes: list[Node], edges: list[Edge], output: str) -> None:
    """Write a self-contained interactive HTML graph visualization."""
    view = Network(height="100vh", directed=True, cdn_resources="in_line")
    view.set_options('''{
      "layout": {"hierarchical": {"enabled": true, "direction": "LR", "levelSeparation": 240, "nodeSpacing": 120}},
      "physics": {"enabled": false},
      "nodes": {"font": {"size": 18}, "margin": 18},
      "edges": {"smooth": {"type": "cubicBezier"}, "font": {"size": 15, "background": "white", "strokeWidth": 6, "strokeColor": "white"}}
    }''')
    for name, label, index in nodes:
        view.add_node(f"{label}:{name}", label=name, title=f"{label} · token {index}", group=label)
    for (source, source_label, _), edge, (target, target_label, _) in edges:
        view.add_edge(f"{source_label}:{source}", f"{target_label}:{target}", label=edge, title=edge)
    view.write_html(output)
    print(f"Interactive graph: {Path(output).resolve()}")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Extract and visualize a schema-constrained graph")
    parser.add_argument("text")
    parser.add_argument("schema", help='e.g. "Nodes: -PERSON (human) -COLOR (color); EDGES: -LIKES (PERSON -> COLOR)"')
    parser.add_argument("-o", "--output", default="graph.html")
    parser.add_argument("--max-distance", type=int, default=50, help="maximum token distance for an edge (default: 50)")
    args = parser.parse_args()

    node_types, edge_types = parse_schema(args.schema)
    client = TypeSafeClient(api_key=os.getenv("API_JEV") or os.environ["API_JEF"])
    state = {"text": args.text, "schema": args.schema}
    nodes = validate_entities(client, state, node_types, run_spacy_ner(args.text))
    edges = detect_edges(client, state, nodes, edge_types, args.max_distance)
    graph = {"nodes": [{"name": n, "type": t, "token_index": i} for n, t, i in nodes], "edges": [{"source": a[0], "type": e, "target": b[0]} for a, e, b in edges]}
    print(json.dumps(graph, indent=2))

    visualize_graph(nodes, edges, args.output)
