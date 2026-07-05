const { useCallback, useEffect, useMemo, useRef, useState } = React;
const {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useEdgesState,
  useNodesState,
  useReactFlow,
  ReactFlowProvider,
  Handle,
  Position
} = window.ReactFlow;

const h = React.createElement;

const icons = {
  topic: "T",
  subtopic: "S",
  concept: "C",
  definition: "D",
  process: "P",
  example: "E",
  formula: "F",
  question: "?",
  insight: "I"
};

const colors = {
  topic: "#67e8f9",
  subtopic: "#93c5fd",
  concept: "#c4b5fd",
  definition: "#86efac",
  process: "#f5d76e",
  example: "#fdba74",
  formula: "#f0abfc",
  question: "#fda4af",
  insight: "#a7f3d0"
};

function api(path, options) {
  return fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options
  }).then(async response => {
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Request failed");
    }
    return data;
  });
}

function layoutGraph(nodes, edges) {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: "LR", nodesep: 70, ranksep: 110, marginx: 40, marginy: 80 });
  nodes.forEach(node => graph.setNode(node.id, { width: 230, height: 98 }));
  edges.forEach(edge => graph.setEdge(edge.source, edge.target));
  dagre.layout(graph);
  return nodes.map(node => {
    const point = graph.node(node.id);
    const pos = node.position ? node.position : { x: point.x - 115, y: point.y - 49 };
    return {
      ...node,
      position: pos,
      targetPosition: "left",
      sourcePosition: "right"
    };
  });
}

function toFlowNode(node, selectedId, matchedId) {
  return {
    id: node.id,
    type: "knowledge",
    data: {
      ...node,
      selected: node.id === selectedId,
      matched: node.id === matchedId
    },
    position: node.position || null
  };
}

function toFlowEdge(edge) {
  return {
    id: `${edge.source}-${edge.target}`,
    source: edge.source,
    target: edge.target,
    label: edge.relationship,
    animated: edge.relationship !== "contains",
    style: { stroke: "rgba(214, 226, 240, 0.58)" },
    labelStyle: { fill: "#cdd8e6", fontSize: 11 },
    labelBgStyle: { fill: "rgba(9, 11, 16, 0.85)" }
  };
}

function KnowledgeNode({ data }) {
  const color = colors[data.type] || colors.concept;
  const className = ["graph-node", data.selected ? "selected" : "", data.matched ? "matched" : ""].join(" ");
  return h(
    "div",
    { className },
    h(Handle, { type: "target", position: Position.Left }),
    h(
      "div",
      { className: "node-head" },
      h("span", { className: "node-icon", style: { color } }, icons[data.type] || "C"),
      h("strong", { className: "node-title" }, data.title)
    ),
    h("span", { className: "node-type" }, data.type),
    h(Handle, { type: "source", position: Position.Right })
  );
}

function AppShell() {
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [videoMeta, setVideoMeta] = useState(null);
  const [graph, setGraph] = useState({ nodes: [], edges: [] });
  const [selectedId, setSelectedId] = useState("");
  const [matchedId, setMatchedId] = useState("");
  const [status, setStatus] = useState("idle");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [history, setHistory] = useState([]);
  const [showAbout, setShowAbout] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const playerRef = useRef(null);

  const selectedNode = useMemo(() => graph.nodes.find(node => node.id === selectedId) || null, [graph.nodes, selectedId]);
  const nodeTypes = useMemo(() => ({ knowledge: KnowledgeNode }), []);

  const stats = useMemo(() => {
    const depthOf = node => {
      let depth = 1;
      let current = node;
      while (current && current.parent) {
        current = graph.nodes.find(item => item.id === current.parent);
        depth += 1;
      }
      return depth;
    };
    return {
      nodes: graph.nodes.length,
      depth: graph.nodes.length ? Math.max(...graph.nodes.map(depthOf)) : 0,
      expanded: graph.nodes.filter(node => node.expanded).length
    };
  }, [graph]);

  async function analyze() {
    setError("");
    setNotice("");
    setStatus("fetching_transcript");
    setGraph({ nodes: [], edges: [] });
    setSelectedId("");
    setMatchedId("");
    try {
      const data = await api("/api/analyze", {
        method: "POST",
        body: JSON.stringify({ youtube_url: youtubeUrl })
      });
      setSessionId(data.session_id);
      setVideoMeta(data.video_meta);
      setGraph(data.overview_graph);
      setSelectedId(data.overview_graph.nodes[0]?.id || "");
      setNotice(data.analysis_notice || "");
      setStatus("ready");
      saveToLocalHistory({
        session_id: data.session_id,
        created_at: Date.now(),
        video_meta: data.video_meta,
        overview_graph: data.overview_graph,
        analysis_notice: data.analysis_notice
      });
    } catch (err) {
      setStatus("idle");
      setError(err.message);
    }
  }

  async function expandNode(nodeId) {
    if (!sessionId || !nodeId) {
      return;
    }
    setError("");
    setStatus("extracting_concepts");
    try {
      const data = await api(`/api/expand/${sessionId}/${nodeId}`, { method: "POST" });
      setGraph(current => {
        const nodes = current.nodes.map(node => node.id === nodeId ? { ...node, expanded: true, children: [...node.children, ...data.new_nodes.map(child => child.id)] } : node);
        return { nodes: [...nodes, ...data.new_nodes], edges: [...current.edges, ...data.new_edges] };
      });
      setStatus("ready");
    } catch (err) {
      setStatus("ready");
      setError(err.message);
    }
  }

  function collapseBranch(nodeId) {
    const remove = new Set();
    const collect = id => {
      graph.nodes.filter(node => node.parent === id).forEach(child => {
        remove.add(child.id);
        collect(child.id);
      });
    };
    collect(nodeId);
    setGraph(current => ({
      nodes: current.nodes.filter(node => !remove.has(node.id)).map(node => node.id === nodeId ? { ...node, expanded: false, children: [] } : node),
      edges: current.edges.filter(edge => !remove.has(edge.source) && !remove.has(edge.target))
    }));
  }

  async function search() {
    if (!sessionId || !query.trim()) {
      return;
    }
    setError("");
    try {
      const data = await api(`/api/search/${sessionId}?q=${encodeURIComponent(query)}`);
      setMatchedId(data.matched_node_id || "");
      if (data.matched_node_id) {
        setSelectedId(data.matched_node_id);
      } else {
        setError("No matching concept found.");
      }
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    fetchHistory();
  }, []);

  function fetchHistory() {
    try {
      const data = JSON.parse(localStorage.getItem("v2g_history") || "[]");
      setHistory(data);
    } catch (e) {
      setHistory([]);
    }
  }

  function saveToLocalHistory(session) {
    try {
      const existing = JSON.parse(localStorage.getItem("v2g_history") || "[]");
      const filtered = existing.filter(item => item.session_id !== session.session_id);
      filtered.unshift(session);
      localStorage.setItem("v2g_history", JSON.stringify(filtered));
      setHistory(filtered);
    } catch(e) {}
  }

  // Auto-save graph state changes to localStorage history
  useEffect(() => {
    if (!sessionId || !graph.nodes || graph.nodes.length === 0) return;
    try {
      const existing = JSON.parse(localStorage.getItem("v2g_history") || "[]");
      const sessionIndex = existing.findIndex(item => item.session_id === sessionId);
      if (sessionIndex !== -1) {
        const currentSession = existing[sessionIndex];
        const graphString = JSON.stringify(graph);
        const storedGraphString = JSON.stringify(currentSession.overview_graph);
        if (storedGraphString !== graphString) {
          currentSession.overview_graph = graph;
          localStorage.setItem("v2g_history", JSON.stringify(existing));
          setHistory(existing);
        }
      }
    } catch (e) {
      console.error("Auto-save failed:", e);
    }
  }, [graph, sessionId]);

  const handleNodeDrag = (nodeId, position) => {
    setGraph(current => {
      const nodes = current.nodes.map(node =>
        node.id === nodeId ? { ...node, position } : node
      );
      return { ...current, nodes };
    });
  };

  async function loadSession(id) {
    const item = history.find(h => h.session_id === id);
    if (!item) return;
    setError("");
    setNotice("");
    setStatus("fetching_transcript");
    setGraph({ nodes: [], edges: [] });
    setSelectedId("");
    setMatchedId("");
    
    // Simulate slight loading delay for UI feedback
    setTimeout(() => {
      setSessionId(item.session_id);
      setVideoMeta(item.video_meta);
      setGraph(item.overview_graph);
      setSelectedId(item.overview_graph.nodes[0]?.id || "");
      setNotice(item.analysis_notice || "");
      setStatus("ready");
    }, 100);
  }

  const [leftWidth, setLeftWidth] = useState(320);
  const [rightWidth, setRightWidth] = useState(360);

  const startResizeLeft = useCallback((e) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = leftWidth;
    const doDrag = (moveEvent) => {
      const deltaX = moveEvent.clientX - startX;
      const newWidth = Math.max(240, Math.min(500, startWidth + deltaX));
      setLeftWidth(newWidth);
    };
    const stopDrag = () => {
      document.removeEventListener("mousemove", doDrag);
      document.removeEventListener("mouseup", stopDrag);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    document.addEventListener("mousemove", doDrag);
    document.addEventListener("mouseup", stopDrag);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [leftWidth]);

  const startResizeRight = useCallback((e) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = rightWidth;
    const doDrag = (moveEvent) => {
      const deltaX = moveEvent.clientX - startX;
      const newWidth = Math.max(260, Math.min(600, startWidth - deltaX));
      setRightWidth(newWidth);
    };
    const stopDrag = () => {
      document.removeEventListener("mousemove", doDrag);
      document.removeEventListener("mouseup", stopDrag);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    document.addEventListener("mousemove", doDrag);
    document.addEventListener("mouseup", stopDrag);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [rightWidth]);

  function seek(timestamp) {
    const seconds = String(timestamp || "0").split(":").reduce((total, part) => total * 60 + Number(part || 0), 0);
    const iframe = playerRef.current;
    if (!iframe || !videoMeta?.video_id) {
      return;
    }
    iframe.contentWindow.postMessage(JSON.stringify({ event: "command", func: "seekTo", args: [seconds, true] }), "*");
    iframe.contentWindow.postMessage(JSON.stringify({ event: "command", func: "playVideo", args: [] }), "*");
  }

  return h(
    "div",
    { className: `app ${isFullscreen ? "fullscreen-mode" : ""}`, style: { gridTemplateColumns: isFullscreen ? "1fr" : `${leftWidth}px 10px minmax(0, 1fr) 10px ${rightWidth}px` } },
    h(LeftPanel, { youtubeUrl, setYoutubeUrl, analyze, videoMeta, playerRef, status, stats, notice, error, history, loadSession, onShowAbout: () => setShowAbout(true) }),
    h("div", { className: "resizer", onMouseDown: startResizeLeft }, h("div", { className: "resizer-line" })),
    h(GraphPanel, { graph, setSelectedId, selectedId, matchedId, nodeTypes, status, query, setQuery, search, isFullscreen, toggleFullscreen: () => setIsFullscreen(!isFullscreen), onNodeDrag: handleNodeDrag }),
    h("div", { className: "resizer", onMouseDown: startResizeRight }, h("div", { className: "resizer-line" })),
    h(RightPanel, { node: selectedNode, graph, setSelectedId, expandNode, collapseBranch, seek }),
    showAbout ? h(AboutModal, { onClose: () => setShowAbout(false) }) : null
  );
}

function LeftPanel({ youtubeUrl, setYoutubeUrl, analyze, videoMeta, playerRef, status, stats, notice, error, history, loadSession, onShowAbout }) {
  const busy = !["idle", "ready"].includes(status);
  const embed = videoMeta?.video_id ? `https://www.youtube.com/embed/${videoMeta.video_id}?enablejsapi=1` : "";
  return h(
    "aside",
    { className: "panel left-panel" },
    h(
      "div",
      { className: "brand" },
      h("div", { className: "brand-row" }, 
        h("h1", null, "V2G"), 
        h("span", { className: "badge" }, "Video to Graph"),
        h("button", { className: "icon-button", title: "About", onClick: onShowAbout, style: { minHeight: "28px", width: "28px", height: "28px", marginLeft: "auto", fontSize: "14px", borderRadius: "50%", padding: 0 } }, "i")
      ),
      h("span", null, "Interactive knowledge exploration")
    ),
    h(
      "div",
      { className: "input-stack" },
      h(
        "div",
        { className: "url-row" },
        h("input", { value: youtubeUrl, onChange: event => setYoutubeUrl(event.target.value), placeholder: "Paste a YouTube URL" }),
        h("button", { className: "icon-button primary", onClick: analyze, disabled: busy, title: "Analyze" }, "→")
      ),
      error ? h("div", { className: "error" }, error) : null,
      notice ? h("div", { className: "notice" }, notice) : null
    ),
    h(
      "div",
      { className: "video-box" },
      embed ? h("iframe", { ref: playerRef, className: "player", src: embed, allow: "autoplay; encrypted-media", allowFullScreen: true }) : h("div", { className: "empty" }, "Paste a YouTube video to build its graph.")
    ),
    videoMeta ? h(
      "div",
      { className: "meta" },
      h("h2", null, videoMeta.title),
      h("div", { className: "muted" }, `Duration ${videoMeta.duration_label}`),
      h("div", { className: status === "ready" ? "success" : "muted" }, labelForStatus(status))
    ) : null,
    history && history.length > 0 ? h(
      "div",
      { className: "history-list" },
      h("h3", { className: "history-title" }, "Recent Videos"),
      history.map(item => h(
        "div",
        { key: item.session_id, className: "history-item", onClick: () => loadSession(item.session_id) },
        h("img", { src: item.video_meta.thumbnail, className: "history-thumb", alt: "" }),
        h("div", { className: "history-info" },
          h("strong", null, item.video_meta.title),
          h("span", null, item.video_meta.duration_label)
        )
      ))
    ) : null,
    h(
      "div",
      { className: "stats" },
      h("div", { className: "stat" }, h("strong", null, stats.nodes), h("span", null, "Nodes")),
      h("div", { className: "stat" }, h("strong", null, stats.depth), h("span", null, "Depth")),
      h("div", { className: "stat" }, h("strong", null, stats.expanded), h("span", null, "Open"))
    )
  );
}

function GraphPanel({ graph, setSelectedId, selectedId, matchedId, nodeTypes, status, query, setQuery, search, isFullscreen, toggleFullscreen, onNodeDrag }) {
  return h(
    "section",
    { className: "panel graph-panel" },
    h(
      "div",
      { className: "topbar" },
      h(
        "div",
        { className: "search-row" },
        h("input", { value: query, onChange: event => setQuery(event.target.value), onKeyDown: event => event.key === "Enter" ? search() : null, placeholder: "Search concepts" }),
        h("button", { onClick: search, title: "Search" }, "⌕")
      ),
      h("button", { className: "fullscreen-btn", onClick: toggleFullscreen, title: "Toggle Fullscreen" }, isFullscreen ? "⤡" : "⤢"),
      h("div", { className: "status-pill" }, labelForStatus(status))
    ),
    h(GraphCanvas, { graph, setSelectedId, selectedId, matchedId, nodeTypes, onNodeDrag })
  );
}

function GraphCanvas({ graph, setSelectedId, selectedId, matchedId, nodeTypes, onNodeDrag }) {
  return h(
    ReactFlowProvider,
    null,
    h(FlowInner, { graph, setSelectedId, selectedId, matchedId, nodeTypes, onNodeDrag })
  );
}

function FlowInner({ graph, setSelectedId, selectedId, matchedId, nodeTypes, onNodeDrag }) {
  const reactFlow = useReactFlow();
  const flowNodes = useMemo(() => layoutGraph(graph.nodes.map(node => toFlowNode(node, selectedId, matchedId)), graph.edges), [graph, selectedId, matchedId]);
  const flowEdges = useMemo(() => graph.edges.map(toFlowEdge), [graph.edges]);
  const [nodes, setNodes, onNodesChange] = useNodesState(flowNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(flowEdges);

  useEffect(() => setNodes(flowNodes), [flowNodes, setNodes]);
  useEffect(() => setEdges(flowEdges), [flowEdges, setEdges]);
  useEffect(() => {
    window.setTimeout(() => reactFlow.fitView({ padding: 0.24, duration: 500 }), 80);
  }, [graph.nodes.length, graph.edges.length, reactFlow]);
  useEffect(() => {
    if (!matchedId) {
      return;
    }
    const node = nodes.find(item => item.id === matchedId);
    if (node) {
      reactFlow.setCenter(node.position.x + 105, node.position.y + 48, { zoom: 1.08, duration: 600 });
    }
  }, [matchedId, nodes, reactFlow]);

  return h(
    "div",
    { className: "flow-wrap" },
    h(ReactFlow, {
      nodes,
      edges,
      nodeTypes,
      onNodesChange,
      onEdgesChange,
      onNodeClick: (_, node) => setSelectedId(node.id),
      onNodeDragStop: (_, node) => onNodeDrag(node.id, node.position),
      fitView: true,
      minZoom: 0.2,
      maxZoom: 1.8
    },
    h(Background, { color: "rgba(255,255,255,0.13)", gap: 24 }),
    h(Controls, null),
    h(MiniMap, { nodeColor: node => colors[node.data.type] || colors.concept, maskColor: "rgba(6, 8, 12, 0.62)", style: { width: 160, height: 110 } })
    )
  );
}

function RightPanel({ node, graph, setSelectedId, expandNode, collapseBranch, seek }) {
  if (!node) {
    return h("aside", { className: "panel right-panel" }, h("div", { className: "empty" }, "Select a node to explore its details."));
  }
  const parent = graph.nodes.find(item => item.id === node.parent);
  const children = graph.nodes.filter(item => item.parent === node.id);
  const related = graph.nodes.filter(item => node.related.map(value => value.toLowerCase()).includes(item.title.toLowerCase()));
  return h(
    "aside",
    { className: "panel right-panel" },
    h(
      "div",
      { className: "details" },
      h("span", { className: "badge" }, node.type),
      h("h2", null, node.title),
      h(DetailSection, { title: "Summary", body: node.summary || "No summary supplied." }),
      node.definition ? h(DetailSection, { title: "Definition", body: node.definition }) : null,
      node.examples?.length ? h(LinkSection, { title: "Examples", items: node.examples.map(value => ({ id: value, title: value })) }) : null,
      node.timestamp ? h(
        "div",
        { className: "detail-section" },
        h("h3", null, "Timestamp"),
        h("button", { className: "chip", onClick: () => seek(node.timestamp) }, node.timestamp)
      ) : null,
      parent ? h(LinkSection, { title: "Parent Topic", items: [parent], onPick: setSelectedId }) : null,
      children.length ? h(LinkSection, { title: "Child Topics", items: children, onPick: setSelectedId }) : null,
      related.length ? h(LinkSection, { title: "Related Concepts", items: related, onPick: setSelectedId }) : null,
      h(
        "div",
        { className: "action-stack" },
        h("button", { className: "wide-button primary", disabled: node.expanded, onClick: () => expandNode(node.id) }, node.expanded ? "Expanded" : "Expand Branch"),
        children.length ? h("button", { className: "wide-button", onClick: () => collapseBranch(node.id) }, "Collapse Branch") : null
      )
    )
  );
}

function DetailSection({ title, body }) {
  return h("div", { className: "detail-section" }, h("h3", null, title), h("p", null, body));
}

function LinkSection({ title, items, onPick }) {
  return h(
    "div",
    { className: "detail-section" },
    h("h3", null, title),
    h("div", { className: "link-list" }, items.map(item => h("button", { key: item.id, className: "chip", onClick: () => onPick ? onPick(item.id) : null }, item.title)))
  );
}

function labelForStatus(status) {
  const labels = {
    idle: "Ready for a video.",
    fetching_transcript: "Fetching transcript...",
    cleaning: "Cleaning transcript...",
    analyzing: "Analyzing...",
    extracting_concepts: "Extracting concepts...",
    building_graph: "Building graph...",
    ready: "Ready."
  };
  return labels[status] || status;
}

function AboutModal({ onClose }) {
  return h(
    "div",
    { className: "modal-overlay", onClick: onClose },
    h(
      "div",
      { className: "modal-content", onClick: e => e.stopPropagation() },
      h("h2", null, "About V2G"),
      h("p", null, "V2G (Video to Graph) is an AI-powered knowledge exploration tool. Paste a YouTube link to extract the transcript and build an interactive knowledge graph of its concepts and topics."),
      h("p", null, "Built with React, Flask, Gemini AI, and yt-dlp. It helps you quickly understand complex videos, expand specific branches of knowledge, and visually navigate concepts."),
      h("button", { className: "wide-button primary", onClick: onClose }, "Close")
    )
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(h(AppShell));
