from pathlib import Path

from pyvis.network import Network

from .models import Edge, Node


def visualize_graph(nodes: list[Node], edges: list[Edge], output: str) -> None:
    """Write a self-contained interactive HTML graph visualization."""
    view = Network(height="100vh", directed=True, cdn_resources="in_line")
    view.set_options('''{
      "layout": {"hierarchical": {"enabled": true, "direction": "LR", "levelSeparation": 240, "nodeSpacing": 120}},
      "physics": {"enabled": false},
      "nodes": {"font": {"size": 18}, "margin": 18},
      "edges": {"smooth": {"type": "cubicBezier"}, "font": {"size": 15, "background": "white", "strokeWidth": 6, "strokeColor": "white"}}
    }''')
    for node in nodes:
        view.add_node(f"{node.type}:{node.name}", label=node.name, title=f"{node.type} · token {node.token_index}", group=node.type)
    for edge in edges:
        view.add_edge(f"{edge.source.type}:{edge.source.name}", f"{edge.target.type}:{edge.target.name}", label=edge.type, title=edge.type)
    view.write_html(output)
    print(f"Interactive graph: {Path(output).resolve()}")
