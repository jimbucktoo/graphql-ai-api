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
            "Below is a summary of the GraphQL schema for the provided endpoint:\n"
            "{schema_summary}\n\n"
            "Based on the schema summary, write a valid GraphQL query for the following prompt:\n"
            "{prompt}\n\n"
            "Return only the GraphQL query."
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
              }
            }
            type {
              name
              kind
            }
          }
        }
      }
    }
    """
    resp = requests.post(endpoint, json={"query": introspection_query})
    resp.raise_for_status()
    return resp.text


def summarize_schema(full_schema: str) -> str:
    """
    Summarize the GraphQL schema to only include the names of object types and a few fields.
    This helps in reducing the token size of the prompt.
    """
    data = json.loads(full_schema)
    types = data.get("data", {}).get("__schema", {}).get("types", [])
    lines = []
    for t in types:
        if t.get("kind") == "OBJECT" and t.get("name") and not t["name"].startswith("__"):
            fields = t.get("fields", [])[:3]
            field_names = [f.get("name") for f in fields]
            lines.append(f"{t['name']}: {', '.join(field_names)}")
    return "\n".join(lines)


def generate_graphql_query(prompt: str, schema_summary: str) -> str:
    """Generate a GraphQL query from a natural language prompt using the LLM."""
    chain = LLMChain(llm=llm, prompt=prompt_template)
    return chain.run(schema_summary=schema_summary, prompt=prompt).strip()


def execute_graphql_query(query: str, endpoint: str) -> dict:
    """Execute the GraphQL query against the given endpoint and return the JSON response."""
    resp = requests.post(endpoint, json={"query": query})
    resp.raise_for_status()
    return resp.json()


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
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    print(f"Starting server on port {port}...")
    app.run(host="0.0.0.0", port=port)
