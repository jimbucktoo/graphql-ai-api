import os
import json
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from langchain import PromptTemplate, LLMChain
from langchain.llms import OpenAI
from graphql import build_client_schema, parse, validate, get_introspection_query

# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Setup LLM
llm = OpenAI(
        temperature=0,
        openai_api_key=OPENAI_API_KEY,
        max_tokens=200
        )

app = Flask(__name__)
CORS(app)

# Prompt template
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

# Helpers
def get_graphql_schema(endpoint: str) -> str:
    introspection_query = get_introspection_query()
    resp = requests.post(endpoint, json={"query": introspection_query})
    resp.raise_for_status()
    return resp.text

def get_type_name(type_obj):
    while type_obj and not type_obj.get("name"):
        type_obj = type_obj.get("ofType", {})
    return type_obj.get("name") or "Unknown"

def summarize_schema(full_schema: str) -> str:
    data = json.loads(full_schema)
    types = data.get("data", {}).get("__schema", {}).get("types", [])
    lines = []
    for t in types:
        if t.get("kind") == "OBJECT" and t.get("name") and not t["name"].startswith("__"):
            fields = t.get("fields", [])[:5]
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
    chain = LLMChain(llm=llm, prompt=prompt_template)
    return chain.run(schema_summary=schema_summary, prompt=prompt).strip()

def generate_query_with_feedback(prompt: str, schema_summary: str, error_msg: str) -> str:
    retry_prompt = (
            f"The previous GraphQL query failed with the following errors:\n"
            f"{error_msg}\n\n"
            f"Prompt: {prompt}\n\n"
            f"Using this schema:\n{schema_summary}\n\n"
            "Please generate a corrected query."
            )
    chain = LLMChain(llm=llm, prompt=prompt_template)
    return chain.run(schema_summary=schema_summary, prompt=retry_prompt).strip()

def validate_query_against_schema(query: str, schema_json: dict) -> list:
    schema = build_client_schema(schema_json["data"])
    parsed_query = parse(query)
    errors = validate(schema, parsed_query)
    return [str(e) for e in errors]

def execute_graphql_query(query: str, endpoint: str) -> dict:
    print("Generated GraphQL Query:\n", query)
    resp = requests.post(endpoint, json={"query": query})
    try:
        resp.raise_for_status()
        json_resp = resp.json()
        if "errors" in json_resp:
            error_messages = [err.get("message", "Unknown error") for err in json_resp["errors"]]
            raise Exception("GraphQL Errors:\n" + "\n".join(error_messages))
        return json_resp
    except requests.HTTPError:
        print("Raw HTTP Error Response:\n", resp.text)
        raise Exception(f"HTTP Error:\n{resp.text}")

# Flask route
@app.route("/query", methods=["POST"])
def query_endpoint():
    data = request.get_json() or {}
    prompt = data.get("prompt")
    endpoint = data.get("endpoint")
    if not prompt or not endpoint:
        return jsonify({"error": "Both 'prompt' and 'endpoint' fields are required"}), 400

    try:
        full_schema_text = get_graphql_schema(endpoint)
        full_schema_json = json.loads(full_schema_text)
        schema_summary = summarize_schema(full_schema_text)

        gql_query = generate_graphql_query(prompt, schema_summary)

        # Validate before sending
        validation_errors = validate_query_against_schema(gql_query, full_schema_json)
        if validation_errors:
            error_str = "\n".join(validation_errors)
            print("Validation errors found. Retrying with feedback...")
            gql_query_retry = generate_query_with_feedback(prompt, schema_summary, error_str)
            retry_validation_errors = validate_query_against_schema(gql_query_retry, full_schema_json)
            if retry_validation_errors:
                return jsonify({
                    "prompt": prompt,
                    "graphql_query_attempted": gql_query,
                    "graphql_query_retry": gql_query_retry,
                    "validation_errors": retry_validation_errors
                    }), 400
            result = execute_graphql_query(gql_query_retry, endpoint)
            return jsonify({
                "prompt": prompt,
                "graphql_query": gql_query_retry,
                "result": result,
                "retried_with_error_feedback": True,
                "original_validation_errors": error_str
                })

        # Query is valid
        result = execute_graphql_query(gql_query, endpoint)
        return jsonify({
            "prompt": prompt,
            "graphql_query": gql_query,
            "result": result
            })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    print(f"Starting server on port {port}...")
    app.run(host="0.0.0.0", port=port)
