from v2g.ai import EDGE_TYPES, make_node
from v2g.text import clean_transcript, estimate_tokens, limit_text_by_tokens, split_semantic_chunks


def create_graph_service(engine):
    return GraphService(engine)


class GraphService:
    def __init__(self, engine):
        self.engine = engine

    def prepare_transcript(self, transcript):
        cleaned = clean_transcript(transcript)
        tokens = estimate_tokens(cleaned)
        limited = tokens > self.engine.config.analysis_token_limit
        analysis_text = limit_text_by_tokens(cleaned, self.engine.config.analysis_token_limit) if limited else cleaned
        chunks = split_semantic_chunks(analysis_text)
        notice = ""
        if limited:
            notice = "Analysis covers the first portion of this video because the transcript exceeded the configured token limit."
        if tokens > self.engine.config.max_transcript_tokens:
            notice = "Analysis covers the first portion of this video because the transcript exceeded the safe processing limit."
        return {
            "cleaned": cleaned,
            "analysis_text": analysis_text,
            "tokens": tokens,
            "chunks": chunks,
            "notice": notice,
        }

    def build_overview(self, transcript, video_meta):
        raw = self.engine.overview(transcript, video_meta)
        nodes = [make_node(item) for item in raw.get("nodes", [])[:15]]
        by_title = {node["title"].lower(): node for node in nodes}
        edges = []
        for edge in raw.get("edges", []):
            source = by_title.get(str(edge.get("source", "")).lower())
            target = by_title.get(str(edge.get("target", "")).lower())
            if source and target and source["id"] != target["id"]:
                self.connect(source, target, edge.get("relationship", "contains"), edges)
        if nodes and not edges:
            root = nodes[0]
            for child in nodes[1:]:
                self.connect(root, child, "contains", edges)
        return {"nodes": nodes, "edges": edges}

    def expand_node(self, graph, node_id, transcript, video_meta):
        node = self.node_by_id(graph, node_id)
        if node["expanded"]:
            return {"new_nodes": [], "new_edges": []}
        ancestors = self.ancestor_chain(graph, node_id)
        siblings = self.sibling_titles(graph, node_id)
        raw = self.engine.expand(transcript, video_meta, node, ancestors, siblings)
        existing_titles = {item["title"].lower() for item in graph["nodes"]}
        new_nodes = []
        new_edges = []
        title_to_node = {node["title"].lower(): node}
        for item in raw.get("nodes", []):
            title = str(item.get("title", "")).strip()
            if not title or title.lower() in existing_titles:
                continue
            child = make_node(item, parent=node_id)
            graph["nodes"].append(child)
            node["children"].append(child["id"])
            new_nodes.append(child)
            title_to_node[child["title"].lower()] = child
            existing_titles.add(child["title"].lower())
        for edge in raw.get("edges", []):
            source = title_to_node.get(str(edge.get("source", "")).lower(), node)
            target = title_to_node.get(str(edge.get("target", "")).lower())
            if target and source["id"] != target["id"]:
                self.connect(source, target, edge.get("relationship", "contains"), graph["edges"], new_edges)
        if new_nodes and not new_edges:
            for child in new_nodes:
                self.connect(node, child, "contains", graph["edges"], new_edges)
        node["expanded"] = True
        return {"new_nodes": new_nodes, "new_edges": new_edges}

    def search(self, graph, query):
        normalized = query.strip().lower()
        if not normalized:
            return {"matched_node_id": "", "path_node_ids": []}
        for node in graph["nodes"]:
            haystack = " ".join([node["title"], node.get("summary", ""), node.get("definition", "")]).lower()
            if normalized in haystack:
                path = [item["id"] for item in self.ancestor_chain(graph, node["id"])]
                return {"matched_node_id": node["id"], "path_node_ids": path}
        return {"matched_node_id": "", "path_node_ids": []}

    def node_by_id(self, graph, node_id):
        for node in graph["nodes"]:
            if node["id"] == node_id:
                return node
        raise KeyError("Node not found")

    def ancestor_chain(self, graph, node_id):
        by_id = {node["id"]: node for node in graph["nodes"]}
        chain = []
        current = by_id.get(node_id)
        while current:
            chain.insert(0, current)
            parent = current.get("parent")
            current = by_id.get(parent)
        return chain

    def sibling_titles(self, graph, node_id):
        node = self.node_by_id(graph, node_id)
        parent = node.get("parent")
        return [item["title"] for item in graph["nodes"] if item.get("parent") == parent and item["id"] != node_id]

    def connect(self, source, target, relationship, edges, extra=None):
        value = relationship if relationship in EDGE_TYPES else "contains"
        edge = {"source": source["id"], "target": target["id"], "relationship": value}
        if not any(item["source"] == edge["source"] and item["target"] == edge["target"] for item in edges):
            edges.append(edge)
            if extra is not None:
                extra.append(edge)
