from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from v2g.ai import GeminiGraphEngine, SarvamGraphEngine, FallbackGraphEngine
from v2g.config import Config
from v2g.graph import create_graph_service
from v2g.sessions import SessionStore
from v2g.youtube import YouTubeService

config = Config()
app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)
limiter = Limiter(get_remote_address, app=app, default_limits=[])
sessions = SessionStore(config.session_ttl_seconds)
youtube = YouTubeService(config)
gemini_engine = GeminiGraphEngine(config)
sarvam_engine = SarvamGraphEngine(config)
engine = FallbackGraphEngine(gemini_engine, sarvam_engine)
graphs = create_graph_service(engine)


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.post("/api/analyze")
@limiter.limit(config.analyze_rate_limit)
def analyze():
    payload = request.get_json(silent=True) or {}
    youtube_url = payload.get("youtube_url", "")
    session_id = sessions.create({"status": "fetching_transcript"})
    try:
        video = youtube.extract_video(youtube_url)
        sessions.update(session_id, status="cleaning")
        prepared = graphs.prepare_transcript(video["transcript"])
        sessions.update(session_id, status="analyzing")
        overview = graphs.build_overview(prepared["analysis_text"], video["meta"])
        sessions.update(session_id, status="building_graph")
        sessions.update(
            session_id,
            status="ready",
            video_meta=video["meta"],
            transcript=prepared,
            graph=overview,
        )
        return jsonify(
            {
                "session_id": session_id,
                "video_meta": video["meta"],
                "overview_graph": overview,
                "analysis_notice": prepared["notice"],
            }
        )
    except Exception as exc:
        import traceback
        traceback.print_exc()
        sessions.delete(session_id)
        return jsonify({"error": str(exc)}), 400


@app.post("/api/expand/<session_id>/<node_id>")
def expand(session_id, node_id):
    session = sessions.get(session_id)
    sessions.update(session_id, status="extracting_concepts")
    result = graphs.expand_node(session["graph"], node_id, session["transcript"]["analysis_text"], session["video_meta"])
    sessions.update(session_id, status="ready", graph=session["graph"])
    return jsonify(result)


@app.get("/api/search/<session_id>")
def search(session_id):
    session = sessions.get(session_id)
    query = request.args.get("q", "")
    result = graphs.search(session["graph"], query)
    return jsonify(result)


@app.get("/api/session/<session_id>/status")
def status(session_id):
    session = sessions.get(session_id)
    return jsonify({"step": session.get("status", "ready")})


@app.get("/api/history")
def history():
    return jsonify(sessions.list_all())


@app.get("/api/session/<session_id>")
def get_session(session_id):
    try:
        session = sessions.get(session_id)
        if session.get("status") != "ready":
            return jsonify({"error": "Session not ready"}), 400
        return jsonify({
            "session_id": session_id,
            "video_meta": session.get("video_meta"),
            "overview_graph": session.get("graph"),
            "analysis_notice": session.get("transcript", {}).get("notice", "") if isinstance(session.get("transcript"), dict) else ""
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 404


@app.errorhandler(Exception)
def handle_exception(e):
    import traceback
    traceback.print_exc()
    return jsonify({"error": "Internal Server Error: " + str(e)}), 500

@app.errorhandler(404)
def not_found(_):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(KeyError)
def expired_session(exc):
    return jsonify({"error": str(exc).strip("'")}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.port, threaded=True)
