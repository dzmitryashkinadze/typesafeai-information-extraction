from pydantic import BaseModel


class Node(BaseModel):
    """A typed entity at a zero-based token position."""

    name: str
    type: str
    token_index: int


class Edge(BaseModel):
    """A typed, directed relationship between two nodes."""

    source: Node
    type: str
    target: Node
