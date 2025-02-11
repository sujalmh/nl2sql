from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from werkzeug.utils import secure_filename
from langchain_openai import ChatOpenAI  # finetuned model
from langchain_community.utilities import SQLDatabase
from langgraph.graph import StateGraph, END
import ast
from typing import TypedDict, List, Optional, Dict
from sqlalchemy import text
from dotenv import load_dotenv
import logging

load_dotenv(override=True)

app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'db'}
HISTORY_WINDOW_SIZE = 10

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize your finetuned model (using the OpenAI ChatCompletion API behind the scenes)
llm = ChatOpenAI(model="ft:gpt-4o-mini-2024-07-18:personal::AzAgjE7R", temperature=0)

db = None
sample_data = None

# We now store history as a list of messages (each message is a dict with "role" and "content")
class QueryState(TypedDict):
    question: str
    history: List[Dict[str, str]]  # e.g., [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
    sql_query: str
    result: Optional[dict]
    retries: int

# The first system prompt: instructs the model how to generate SQL queries.
SYSTEM_PROMPT = """You are an extremely precise SQL expert analyzing economic data in a conversation. Your goal is to generate only valid, executable SQL queries. You MUST follow these instructions exactly. Pay very close attention to the conversation history and to error messages to refine your queries.

When the question is vague or requires summarization:
- Identify and select only the columns relevant to the question.
- Use appropriate aggregations (e.g., SUM, AVG, COUNT) or grouping when the question asks for trends or summaries.
- If the question asks about trends over time (e.g., monthly, quarterly), group by the Month or Year column as appropriate.
- If the question asks about factors affecting inflation or trends, consider aggregating on Inflation (%) and selecting relevant columns such as State, Sector, or Group.

Handling Follow-up Questions:
When you receive a new question, consider the conversation history to understand the user's evolving information needs.
- Identify Semantic Context: Focus on the overall meaning and topic of the conversation, not just keywords.  Understand the user's underlying intent.
- Recognize Question Type: Determine if the new question is a refinement, specification, or related question to the previous turns. Is it asking for similar information but with different parameters, or a completely new topic?
- Maintain Semantic Consistency: If the current question is semantically related to the previous ones, try to maintain consistency in the query structure (e.g., columns, aggregations) while adjusting filters or groupings as needed. For very short follow-up questions (like single words or years),  infer the implied intent from the semantic context of the conversation.  **However, be cautious not to over-infer context if the new question introduces a significantly different topic or data requirement.**
- Independent Questions: If the new question appears to be unrelated to the conversation history, generate a new SQL query from scratch, disregarding prior context.

Generate SQL queries for SQLite following these rules:
1. Return a single SQL query per question.
2. Select necessary columns to support user question.
3. Check previous questions in the conversation history to provide context and maintain semantic consistency where appropriate.
4. Use only existing columns from {table_info}.
5. Escape reserved keywords with backticks (`).
6. Return only the SQL query without Markdown (dont wrap with ```sql).
7. Use `LIMIT {top_k}` when results need to be restricted.

Available tables:
{table_info}

Here are some sample rows from the database to understand the structure:
{sample_data}

"""


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/api/upload', methods=['POST'])
def upload_file():
    global db, sample_data
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        db = SQLDatabase.from_uri(f"sqlite:///{filepath}")
        query = "SELECT * FROM data LIMIT 5;"
        sample_data = db.run(query, fetch="cursor")
        
        return jsonify({'message': 'File uploaded successfully'}), 200

    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/api/ask', methods=['POST'])
def ask_question():
    global db
    if not db:
        return jsonify({'error': 'Database not uploaded yet'}), 400

    data = request.json
    question = data.get('question')
    # Expecting history as a list of message dicts, e.g.,
    # [{"role": "user", "content": "first question"}, {"role": "assistant", "content": "first answer"}]
    history = data.get('history', [])

    if not question:
        return jsonify({'error': 'No question provided'}), 400

    state: QueryState = {
        "question": question,
        "history": history,
        "sql_query": "",
        "result": None,
        "retries": 0
    }

    graph = create_graph()
    try:
        result_state = graph.invoke(state)
        return jsonify({
            'sql_query': result_state['sql_query'],
            'result': result_state['result'],
            'history': result_state['history']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
def create_graph():
    def generate_query(state: QueryState) -> QueryState:
        logging.info(f"generate_query: Input State: {state}")
        
        messages = []
        # Start with the system prompt
        messages.append({"role": "system", "content": SYSTEM_PROMPT.format(table_info=db.get_table_info(), sample_data=sample_data, top_k=5)
})
        # Add table information and sample data as context
        table_info = db.get_table_info()
        sample_data_str = str(sample_data)
        messages.append({
            "role": "system",
            "content": f"Table Information:\n{table_info}\nSample Data:\n{sample_data_str}"
        })
        # Append any previous conversation history
        if state.get("history"):
            messages.extend(state["history"])
        # Append the current question
        messages.append({"role": "user", "content": state["question"]})
        
        # Invoke the finetuned model using the standard ChatCompletion API call
        response = llm.invoke(messages)
        # Assume the response is an object with a 'content' attribute;
        # otherwise, adjust as necessary.
        sql_query = response.content.strip() if hasattr(response, "content") else response.strip()
        
        # Update history with the current turn
        new_history = state.get("history", []) + [
            {"role": "user", "content": state["question"]},
            {"role": "assistant", "content": sql_query}
        ]
        
        output_state = {
            "sql_query": sql_query,
            "history": new_history,
            "question": state["question"],
            "retries": state.get("retries", 0),
            "result": None
        }
        logging.info(f"generate_query: Output State: {output_state}")
        return output_state

    def execute_query(state: QueryState) -> QueryState:
        logging.info(f"execute_query: Input State: {state}")
        try:
            query = state["sql_query"]
            result = {"columns": [], "data": []}

            raw_query_result = db.run(query, fetch="cursor")
            query_result = list(raw_query_result.mappings())

            if query_result:
                result["columns"] = list(query_result[0].keys())
                result["data"] = [dict(row) for row in query_result]

            output_state = {
                "result": result,
                "history": state["history"],
                "sql_query": state["sql_query"],
                "question": state["question"],
                "retries": state["retries"]
            }
            logging.info(f"execute_query: Output State: {output_state}")
            return output_state
        except Exception as e:
            error_result = {"error": str(e)}
            output_state = {
                "result": error_result,
                "history": state["history"],
                "sql_query": state["sql_query"],
                "question": state["question"],
                "retries": state["retries"]
            }
            logging.info(f"execute_query: Error Output State: {output_state}")
            return output_state

    def prepare_retry(state: QueryState) -> QueryState:
        logging.info(f"prepare_retry: Input State: {state}")
        new_retries = state["retries"] + 1
        error_message = state["result"].get("error", "Unknown error")
        # Add the error message to the history as a system message for context.
        new_history = state["history"] + [
            {"role": "system", "content": f"Previous SQL error: {error_message}"}
        ]
        output_state = {
            **state,
            "retries": new_retries,
            "history": new_history
        }
        logging.info(f"prepare_retry: Output State: {output_state}")
        return output_state

    def should_retry(state: QueryState) -> bool:
        logging.info(f"should_retry: Input State: {state}")
        has_error = "error" in state.get("result", {})
        retries = state.get("retries", 0)
        should_retry_val = has_error and retries < 3
        logging.info(f"should_retry: has_error={has_error}, retries={retries}, should_retry_val={should_retry_val}")
        return should_retry_val

    graph = StateGraph(QueryState)
    graph.add_node("generate_query", generate_query)
    graph.add_node("execute_query", execute_query)
    graph.add_node("prepare_retry", prepare_retry)
    graph.set_entry_point("generate_query")
    graph.add_edge("generate_query", "execute_query")
    graph.add_conditional_edges(
        "execute_query",
        should_retry,
        {
            True: "prepare_retry",
            False: END
        }
    )
    graph.add_edge("prepare_retry", "generate_query")
    return graph.compile()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)  # Enable logging
    app.run(debug=True)
