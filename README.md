# graphql-ai-api

GraphQLAI converts plain English requests into precise, ready-to-use GraphQL queries, simplifying and speeding up data fetching.

## Links

- [GraphQLAI Front-End](https://graphql-ai.surge.sh/) - GraphQLAI Front-End Application
- [GraphQLAI Back-End](https://graphql-ai-api.onrender.com) - GraphQLAI Back-End Server
- [GraphQLAI Repository](https://github.com/jimbucktoo/graphql-ai/) - GraphQLAI Github Repository
- [GraphQLAI API Repository](https://github.com/jimbucktoo/graphql-ai-api/) - GraphQLAI API Github Repository

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/jimbucktoo/graphql-ai-api.git
cd graphql-ai-api
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up environment variables

Create a .env file in the root directory and add the following:

```
OPENAI_API_KEY=your_openai_api_key
```

### 5. Run the application

```bash
python app.py
```

### 6. Make a request

```
POST http://localhost:10000/query
Content-Type: application/json

{
    "prompt": "Get the titles of all movies",
    "endpoint": "https://moviecrud.onrender.com/graphql"
}
```

## Technologies

- [Flask](https://flask.palletsprojects.com/en/3.0.x/) - Flask is a micro web framework written in Python.
- [Python](https://www.python.org/) - Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation.

## Authors

- **James Liang** - _Initial work_ - [jimbucktoo](https://github.com/jimbucktoo/)
