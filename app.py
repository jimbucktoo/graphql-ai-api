import os
import json
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from langchain import PromptTemplate, LLMChain
from langchain.llms import OpenAI

# Load environment variables from .env file
load_dotenv()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Configure the OpenAI LLM with LangChain
llm = OpenAI(
        temperature=0,
        openai_api_key=OPENAI_API_KEY,
        max_tokens=200  # Limit the completion tokens
        )

app = Flask(__name__)
CORS(app)

# Prompt template for generating GraphQL queries
prompt_template = PromptTemplate(
        input_variables=["schema_summary", "prompt"],
        template=(
            "Schema summary:\n{schema_summary}\n\n"
            "Your task is to convert the user's natural language request into a valid GraphQL query.\n"
            "Include required arguments, return useful fields, and follow correct syntax.\n\n"
            "User request: {prompt}\n\n"
            "GraphQL query:"
            )
        )

def get_graphql_schema(endpoint: str) -> str:
    """Retrieve the full GraphQL schema using an introspection query."""
    introspection_query = """
    query IntrospectionQuery {
      __schema {
        types {
          name
          kind
          description
          fields {
            name
            description
            args {
              name
              description
              type {
                name
                kind
                ofType {
                  name
                  kind
                }
              }
            }
            type {
              name
              kind
              ofType {
                name
                kind
              }
            }
          }
        }
      }
    }
    """
    resp = requests.post(endpoint, json={"query": introspection_query})
    resp.raise_for_status()
    return resp.text

def get_type_name(type_obj):
    """Helper to extract the actual type name (unwraps nested ofType)."""
    while type_obj and not type_obj.get("name"):
        type_obj = type_obj.get("ofType", {})
    return type_obj.get("name") or "Unknown"

def summarize_schema(full_schema: str) -> str:
    """
    Summarize the GraphQL schema to include object types, field names, types, and arguments.
    """
    data = json.loads(full_schema)
    types = data.get("data", {}).get("__schema", {}).get("types", [])
    lines = []
    for t in types:
        if t.get("kind") == "OBJECT" and t.get("name") and not t["name"].startswith("__"):
            fields = t.get("fields", [])[:5]  # Include first 5 fields for brevity
            field_lines = []
            for f in fields:
                field_name = f.get("name")
                field_type = get_type_name(f.get("type", {}))
                args = f.get("args", [])
                if args:
                    args_str = ", ".join(
                            f"{arg['name']}: {get_type_name(arg['type'])}"
                            for arg in args
                            )
                    field_lines.append(f"{field_name}({args_str}): {field_type}")
                else:
                    field_lines.append(f"{field_name}: {field_type}")
            if field_lines:
                lines.append(f"{t['name']} {{\n  " + "\n  ".join(field_lines) + "\n}}")
    return "\n\n".join(lines)

def generate_graphql_query(prompt: str, schema_summary: str) -> str:
    """Generate a GraphQL query from a natural language prompt using the LLM."""
    chain = LLMChain(llm=llm, prompt=prompt_template)
    return chain.run(schema_summary=schema_summary, prompt=prompt).strip()

def execute_graphql_query(query: str, endpoint: str) -> dict:
    """Execute the GraphQL query against the given endpoint and return the JSON response."""
    print("Generated GraphQL Query:\n", query)  # Debug logging
    resp = requests.post(endpoint, json={"query": query})
    try:
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        print("GraphQL Error Response:\n", resp.text)  # Debug logging
        # Include the raw GraphQL error response in the returned error
        raise Exception(f"GraphQL Error:\n{resp.text}")

@app.route("/query", methods=["POST"])
def query_endpoint():
    """
    Accepts JSON with:
      - prompt: natural language prompt
      - endpoint: GraphQL endpoint URL

    Generates and executes a query, returning both the GraphQL query and its results.
    """
    data = request.get_json() or {}
    prompt = data.get("prompt")
    endpoint = data.get("endpoint")
    if not prompt or not endpoint:
        return jsonify({"error": "Both 'prompt' and 'endpoint' fields are required"}), 400

    try:
        # Fetch and summarize schema for this endpoint
        full_schema = get_graphql_schema(endpoint)
        schema_summary = summarize_schema(full_schema)

        # Generate and execute
        gql_query = generate_graphql_query(prompt, schema_summary)
        result = execute_graphql_query(gql_query, endpoint)

        return jsonify({
            "prompt": prompt,
            "endpoint": endpoint,
            "graphql_query": gql_query,
            "result": result
            })
    except Exception as e:
        return jsonify({
            "error": str(e)
            }), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    print(f"Starting server on port {port}...")
    app.run(host="0.0.0.0", port=port)
