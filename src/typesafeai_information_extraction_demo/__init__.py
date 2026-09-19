import argparse
import json
import os
import re

from dotenv import load_dotenv
from typesafe_sdk import TypeSafeClient

from .extraction import detect_edges, validate_entities
from .ner import run_spacy_ner
from .visualization import visualize_graph


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


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Extract and visualize a schema-constrained graph")
    parser.add_argument("text")
    parser.add_argument("schema", help='e.g. "Nodes: -PERSON (human) -COLOR (color); EDGES: -LIKES (PERSON -> COLOR)"')
    parser.add_argument("-o", "--output", default="graph.html")
    parser.add_argument("--max-distance", type=int, default=10, help="maximum token distance for an edge (default: 50)")
    args = parser.parse_args()

    node_types, edge_types = parse_schema(args.schema)
    client = TypeSafeClient(api_key=os.getenv("API_JEV") or os.environ["API_JEF"])
    state = {"text": args.text, "schema": args.schema}
    nodes = validate_entities(client, state, node_types, run_spacy_ner(args.text))
    edges = detect_edges(client, state, nodes, edge_types, args.max_distance)
    graph = {"nodes": [node.model_dump() for node in nodes], "edges": [edge.model_dump() for edge in edges]}
    print(json.dumps(graph, indent=2))

    visualize_graph(nodes, edges, args.output)
