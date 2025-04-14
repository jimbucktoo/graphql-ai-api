import os
import json
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from langchain import PromptTemplate, LLMChain
from langchain.llms import OpenAI

# Load environment variables from .env file
load_dotenv()
GRAPHQL_ENDPOINT = os.environ.get("GRAPHQL_ENDPOINT")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Configure the OpenAI LLM with Langchain
llm = OpenAI(
        temperature=0,
        openai_api_key=OPENAI_API_KEY,
        max_tokens=200  # Limit the completion tokens
        )

app = Flask(__name__)

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
    response = requests.post(endpoint, json={"query": introspection_query})
    if response.status_code == 200:
        return response.text  # Return the raw JSON string
    else:
        raise Exception(f"Failed to fetch GraphQL schema: {response.text}")

def summarize_schema(full_schema: str) -> str:
    """
    Summarize the GraphQL schema to only include the names of object types and a few fields.
    This helps in reducing the token size of the prompt.
    """
    try:
        schema_data = json.loads(full_schema)
    except json.JSONDecodeError:
        raise Exception("Invalid schema JSON")

    summary_lines = []
    types = schema_data.get("data", {}).get("__schema", {}).get("types", [])
    for type_info in types:
        # Filter for object types with a non-empty name that don't start with '__'
        if type_info.get("kind") == "OBJECT" and type_info.get("name") and not type_info["name"].startswith("__"):
            type_name = type_info["name"]
            fields = type_info.get("fields", [])
            # List first 3 field names (if available) for brevity
            field_names = [field.get("name", "") for field in fields[:3]]
            summary_lines.append(f"{type_name}: {', '.join(field_names)}")
    summary = "\n".join(summary_lines)
    return summary

# Fetch and summarize the schema (you could cache this result if necessary)
try:
    full_schema = get_graphql_schema(GRAPHQL_ENDPOINT)
    graphql_schema_summary = summarize_schema(full_schema)
except Exception as e:
    graphql_schema_summary = "Unable to fetch schema"
    print(f"Schema error: {str(e)}")

# Define the prompt template using the schema summary
prompt_template = PromptTemplate(
        input_variables=["schema_summary", "question"],
        template=(
            "Below is a summary of the GraphQL schema:\n"
            "{schema_summary}\n\n"
            "Based on the schema summary, write a valid GraphQL query for the following question:\n"
            "{question}\n\n"
            "Return only the GraphQL query."
            )
        )

def generate_graphql_query(question: str, schema_summary: str) -> str:
    """Generate a GraphQL query from a natural language question using the LLM."""
    chain = LLMChain(llm=llm, prompt=prompt_template)
    query = chain.run(schema_summary=schema_summary, question=question)
    print(query)
    return query.strip()

def execute_graphql_query(query: str, endpoint: str) -> dict:
    """Execute the GraphQL query against the given endpoint and return the JSON response."""
    response = requests.post(endpoint, json={"query": query})
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Query execution failed: {response.text}")

@app.route("/query", methods=["POST"])
def query_endpoint():
    """
    Endpoint to accept a natural language query, generate a GraphQL query, execute it,
    and return both the GraphQL query and its results.
    """
    data = request.get_json()
    question = data.get("question", "")
    if not question:
        return jsonify({"error": "Question is required"}), 400

    try:
        # Generate the GraphQL query using the schema summary
        graphql_query = generate_graphql_query(question, graphql_schema_summary)
        # Execute the generated GraphQL query
        result = execute_graphql_query(graphql_query, GRAPHQL_ENDPOINT)
        return jsonify({
            "question": question,
            "graphql_query": graphql_query,
            "result": result
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Run the Flask app
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    print(f"Starting server on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)
