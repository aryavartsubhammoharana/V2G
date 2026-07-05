import json
import requests
from uuid import uuid4

from google import genai
from google.genai import types


NODE_TYPES = ["topic", "subtopic", "concept", "definition", "process", "example", "formula", "question", "insight"]
EDGE_TYPES = ["contains", "requires", "causes", "explains", "related_to", "part_of", "depends_on", "example_of", "improves", "uses"]

GRAPH_SCHEMA = {
    "type": "object",
    "properties": {
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "type": {"type": "string", "enum": NODE_TYPES},
                    "summary": {"type": "string"},
                    "definition": {"type": "string"},
                    "examples": {"type": "array", "items": {"type": "string"}},
                    "timestamp": {"type": "string"},
                    "related": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "type", "summary"],
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "relationship": {"type": "string", "enum": EDGE_TYPES},
                },
                "required": ["source", "target", "relationship"],
            },
        },
    },
    "required": ["nodes", "edges"],
}


class GeminiGraphEngine:
    def __init__(self, config):
        self.config = config
        self.client = genai.Client(api_key=config.gemini_api_key) if config.gemini_api_key else None

    def overview(self, transcript, video_meta):
        prompt = {
            "task": "Create the first overview level of a video knowledge graph with 10 to 15 highest-level concepts only.",
            "video": video_meta,
            "transcript": transcript,
            "rules": [
                "This is not a summary.",
                "Return concepts users can explore.",
                "Use timestamp values when supported by the transcript, otherwise use an empty string.",
                "Edges should connect broader ideas to narrower ideas.",
            ],
        }
        return self.generate_graph(prompt)

    def expand(self, transcript, video_meta, node, ancestors, siblings):
        prompt = {
            "task": "Expand only the clicked node with deeper child concepts from the video.",
            "video": video_meta,
            "clicked_node": node,
            "ancestor_chain": ancestors,
            "existing_sibling_titles": siblings,
            "transcript": transcript,
            "rules": [
                "Return only new children of the clicked node and direct relationship edges.",
                "Avoid duplicates and concepts overlapping with siblings.",
                "Prefer specific concepts, examples, definitions, processes, questions, formulas, and insights from the video.",
                "Do not regenerate the whole graph.",
            ],
        }
        return self.generate_graph(prompt)

    def generate_graph(self, prompt):
        if not self.client:
            raise ValueError("GEMINI_API_KEY is required for graph extraction.")
        text = json.dumps(prompt, ensure_ascii=False)
        response = self.client.models.generate_content(
            model=self.config.gemini_model,
            contents=text,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GRAPH_SCHEMA,
                temperature=0.2,
            ),
        )
        return self.parse_json(response.text)

    def parse_json(self, text):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            repaired = self.repair_json(text)
            return json.loads(repaired)

    def repair_json(self, malformed):
        if not self.client:
            raise ValueError("Gemini returned malformed JSON and repair is unavailable.")
        response = self.client.models.generate_content(
            model=self.config.gemini_model,
            contents=json.dumps({"task": "Repair this into valid JSON matching the supplied graph schema.", "malformed": malformed}),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GRAPH_SCHEMA,
                temperature=0,
            ),
        )
        return response.text


def make_node(raw, parent=""):
    return {
        "id": str(uuid4()),
        "title": str(raw.get("title", "Untitled")).strip()[:120] or "Untitled",
        "type": raw.get("type") if raw.get("type") in NODE_TYPES else "concept",
        "summary": str(raw.get("summary", "")).strip(),
        "definition": str(raw.get("definition", "")).strip(),
        "examples": raw.get("examples") if isinstance(raw.get("examples"), list) else [],
        "timestamp": str(raw.get("timestamp", "")).strip(),
        "expanded": False,
        "parent": parent,
        "children": [],
        "related": raw.get("related") if isinstance(raw.get("related"), list) else [],
    }

class SarvamGraphEngine:
    def __init__(self, config):
        self.config = config

    def overview(self, transcript, video_meta):
        prompt = {
            "task": "Create the first overview level of a video knowledge graph with 10 to 15 highest-level concepts only.",
            "video": video_meta,
            "transcript": transcript,
            "rules": [
                "This is not a summary.",
                "Return concepts users can explore.",
                "Use timestamp values when supported by the transcript, otherwise use an empty string.",
                "Edges should connect broader ideas to narrower ideas.",
                "MUST RETURN A VALID JSON OBJECT MATCHING THE GRAPH_SCHEMA.",
            ],
        }
        return self.generate_graph(prompt)

    def expand(self, transcript, video_meta, node, ancestors, siblings):
        prompt = {
            "task": "Expand only the clicked node with deeper child concepts from the video.",
            "video": video_meta,
            "clicked_node": node,
            "ancestor_chain": ancestors,
            "existing_sibling_titles": siblings,
            "transcript": transcript,
            "rules": [
                "Return only new children of the clicked node and direct relationship edges.",
                "Avoid duplicates and concepts overlapping with siblings.",
                "Prefer specific concepts, examples, definitions, processes, questions, formulas, and insights from the video.",
                "Do not regenerate the whole graph.",
                "MUST RETURN A VALID JSON OBJECT MATCHING THE GRAPH_SCHEMA.",
            ],
        }
        return self.generate_graph(prompt)

    def generate_graph(self, prompt):
        if not self.config.sarvam_api_key:
            raise ValueError("SARVAM_API_KEY is required.")
        
        system_msg = "You are a knowledge graph AI. You MUST output ONLY valid JSON matching the schema provided by the user. Do not include markdown code blocks or conversational text. Output raw JSON only."
        schema_info = f"Ensure the output conforms exactly to this JSON schema: {json.dumps(GRAPH_SCHEMA)}"
        
        user_msg = f"{json.dumps(prompt)}\n\n{schema_info}"
        
        headers = {
            "api-subscription-key": self.config.sarvam_api_key,
            "Content-Type": "application/json"
        }
        data = {
            "model": self.config.sarvam_model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg}
            ],
            "temperature": 0.2
        }
        
        resp = requests.post("https://api.sarvam.ai/v1/chat/completions", headers=headers, json=data)
        resp.raise_for_status()
        
        resp_json = resp.json()
        if "choices" not in resp_json or not resp_json["choices"]:
            raise ValueError(f"Sarvam API response has no choices: {resp_json}")
            
        choice = resp_json["choices"][0]
        message = choice.get("message", {})
        content = message.get("content")
        
        if not content:
            refusal = message.get("refusal")
            raise ValueError(f"Sarvam API returned empty content. Refusal: {refusal}. Raw response: {resp.text}")
            
        content = content.strip()
        if content.startswith("```json"):
            content = content.replace("```json", "", 1)
        if content.startswith("```"):
            content = content.replace("```", "", 1)
        if content.endswith("```"):
            content = content[:-3]
            
        return self.parse_json(content.strip())
        
    def parse_json(self, text):
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON response: {e}\nRaw output: {text}")

class FallbackGraphEngine:
    def __init__(self, primary, secondary):
        self.primary = primary
        self.secondary = secondary
        self.config = primary.config
    def overview(self, transcript, video_meta):
        try:
            return self.primary.overview(transcript, video_meta)
        except Exception as e:
            print("Primary engine failed during overview, falling back to secondary:", e)
            return self.secondary.overview(transcript, video_meta)
            
    def expand(self, transcript, video_meta, node, ancestors, siblings):
        try:
            return self.primary.expand(transcript, video_meta, node, ancestors, siblings)
        except Exception as e:
            print("Primary engine failed during expand, falling back to secondary:", e)
            return self.secondary.expand(transcript, video_meta, node, ancestors, siblings)
