from itertools import product

from typesafe_sdk import Choice, Noul, TypeSafeClient

from .models import Edge, Node


def validate_entities(client: TypeSafeClient, state: dict[str, str], types: dict[str, str], candidates: list[tuple[str, int]]) -> list[Node]:
    """Use TypeSafe AI to retain and type valid entity candidates."""
    result = client.system_one(state, {f"n{i}": Choice(instructions=f"Classify candidate {name!r} using the schema; choose NONE unless it is an entity mentioned in the text.", criteria={**types, "NONE": "Not an entity of any allowed node type."}) for i, (name, _) in enumerate(candidates)})
    return [Node(name=name, type=result.answers[f"n{i}"].choice, token_index=index) for i, (name, index) in enumerate(candidates) if result.answers[f"n{i}"].choice != "NONE"]


def detect_edges(client: TypeSafeClient, state: dict[str, str], nodes: list[Node], types: list[tuple[str, str, str]], max_distance: int) -> list[Edge]:
    """Use TypeSafe AI to detect edges between nearby, type-compatible nodes."""
    possible = [(a, edge, b) for edge, source, target in types for a, b in product(nodes, repeat=2) if a.type == source and b.type == target and a != b and abs(a.token_index - b.token_index) <= max_distance]
    result = client.system_one(state, {f"e{i}": Noul(instructions=f"The text asserts as true that {a.name!r} {edge} {b.name!r}. Resolve references, but answer false for negated, hypothetical, or uncertain claims.") for i, (a, edge, b) in enumerate(possible)}) if possible else None
    return [Edge(source=a, type=edge, target=b) for i, (a, edge, b) in enumerate(possible) if result.answers[f"e{i}"].noul >= .7]
