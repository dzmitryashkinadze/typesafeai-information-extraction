# TypeSafe AI knowledge graph

A deliberately tiny knowledge-graph extractor: spaCy proposes entities, TypeSafe AI validates their schema types and relationships, and PyVis writes a self-contained interactive HTML graph.

## Run

Put these values in `.env`:

```dotenv
API_JEV=...
```

Install and run with `uv`:

```bash
uv sync
uv run typesafeai-information-extraction-demo \
  "Out of Jane, Alex, and Mary only Mary likes pink. Other two like blue. Nobody knows if Jack likes brown." \
  "Nodes: -PERSON (human) -COLOR (color); EDGES: -LIKES"
```

The command prints the extracted JSON and creates `graph.html`; open it in any browser to drag, zoom, and inspect the graph. Use `--output another-name.html` to choose another path. Node and edge names must be uppercase identifiers.
