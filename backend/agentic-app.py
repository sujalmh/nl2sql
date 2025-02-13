
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from werkzeug.utils import secure_filename
from langchain_openai import ChatOpenAI  # finetuned model for SQL generation
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

# Initialize your two ChatCompletion models:
# One for generating SQL queries (agentic behavior)
llm = ChatOpenAI(model="ft:gpt-4o-mini-2024-07-18:personal::AzAgjE7R", temperature=0)
# And a second one for explaining what the agent is doing
explanation_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

db = None
sample_data = None

# Extend QueryState to include intermediate reasoning steps.
class QueryState(TypedDict):
    question: str
    history: List[Dict[str, str]]  # [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
    sql_query: str
    result: Optional[dict]
    retries: int
    complexity_stage: str  # "simple" or "complex"
    explanation: Optional[str]
    # New field to store intermediate chain-of-thought messages.
    intermediate_reasoning: List[str]

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
    history = data.get('history', [])

    if not question:
        return jsonify({'error': 'No question provided'}), 400

    state: QueryState = {
        "question": question,
        "history": history,
        "sql_query": "",
        "result": None,
        "retries": 0,
        "complexity_stage": "simple",  # start with a simple query
        "explanation": None,
        "intermediate_reasoning": []  # start with an empty list of reasoning messages
    }

    graph = create_graph()
    try:
        result_state = graph.invoke(state)
        return jsonify({
            'sql_query': result_state['sql_query'],
            'result': result_state['result'],
            'history': result_state['history'],
            'explanation': result_state.get('explanation', ''),
            'reasoning': result_state.get('intermediate_reasoning', [])
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def create_graph():
    def generate_query(state: QueryState) -> QueryState:
        logging.info(f"generate_query: Input State: {state}")
        complexity_stage = state.get("complexity_stage", "simple")
        additional_instruction = ""
        if complexity_stage == "simple":
                additional_instruction = "\nPlease generate a simple SQL query that directly answers the question. Keep it basic so that it can serve as a foundation for further refinement."
        elif complexity_stage == "complex":
            additional_instruction = "\nPlease generate a more complex query that builds upon your previous simple query by adding appropriate aggregations, filters, or analysis. Ensure that the final query adheres strictly to the original input prompt."
        else:
            additional_instruction = ""

        messages = []
        messages.append({
            "role": "system",
            "content": SYSTEM_PROMPT.format(
                table_info=db.get_table_info(),
                sample_data=sample_data,
                top_k=5
            )
        })

        table_info = db.get_table_info()
        sample_data_str = str(sample_data)
        messages.append({
            "role": "system",
            "content": f"Table Information:\n{table_info}\nSample Data:\n{sample_data_str}"
        })

        if state.get("history"):
            messages.extend(state["history"])

        question_text = state["question"] + additional_instruction
        messages.append({"role": "user", "content": question_text})
        
        response = llm.invoke(messages)
        sql_query = response.content.strip() if hasattr(response, "content") else response.strip()

        # Append the generated query as an intermediate reasoning step.
        state["intermediate_reasoning"].append(f"[Simple Query Generated] {sql_query}")

        new_history = state.get("history", []) + [
            {"role": "user", "content": question_text},
            {"role": "assistant", "content": sql_query}
        ]
        
        output_state = {
            "sql_query": sql_query,
            "history": new_history,
            "question": state["question"],
            "retries": state.get("retries", 0),
            "result": None,
            "complexity_stage": complexity_stage,
            "explanation": state.get("explanation"),
            "intermediate_reasoning": state["intermediate_reasoning"]
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
            
            # Append execution result to the reasoning log.
            state["intermediate_reasoning"].append(f"[Executed Query] Returned {len(result.get('data', []))} rows.")

            output_state = {
                "result": result,
                "history": state["history"],
                "sql_query": state["sql_query"],
                "question": state["question"],
                "retries": state["retries"],
                "complexity_stage": state["complexity_stage"],
                "explanation": state.get("explanation"),
                "intermediate_reasoning": state["intermediate_reasoning"]
            }
            logging.info(f"execute_query: Output State: {output_state}")
            return output_state
        except Exception as e:
            error_result = {"error": str(e)}
            state["intermediate_reasoning"].append(f"[Execution Error] {str(e)}")
            output_state = {
                "result": error_result,
                "history": state["history"],
                "sql_query": state["sql_query"],
                "question": state["question"],
                "retries": state["retries"],
                "complexity_stage": state["complexity_stage"],
                "explanation": state.get("explanation"),
                "intermediate_reasoning": state["intermediate_reasoning"]
            }
            logging.info(f"execute_query: Error Output State: {output_state}")
            return output_state

    def prepare_retry(state: QueryState) -> QueryState:
        logging.info(f"prepare_retry: Input State: {state}")
        new_retries = state["retries"] + 1
        result = state.get("result", {})

        if "error" in result:
            error_message = result.get("error", "Unknown error")
        elif result.get("columns") == [] and result.get("data") == []:
            error_message = "Empty result set"
        else:
            error_message = "Unknown issue"
            
        state["intermediate_reasoning"].append(f"[Retry {new_retries}] Reason: {error_message}")

        new_history = state["history"] + [
            {"role": "system", "content": f"Previous SQL error: {error_message}"}
        ]
        output_state = {
            **state,
            "retries": new_retries,
            "history": new_history,
            "intermediate_reasoning": state["intermediate_reasoning"]
        }
        logging.info(f"prepare_retry: Output State: {output_state}")
        return output_state

    def complexify_query(state: QueryState) -> QueryState:
        logging.info(f"complexify_query: Input State: {state}")
        messages = []
        messages.append({
            "role": "system",
            "content": (
                "You are an expert SQL agent. The previous query executed successfully. "
                "Now, please refine and expand the query to include additional aggregations, filters, or analysis as appropriate. "
                "Make sure that the revised query remains strictly faithful to the original question and input prompt."
            )
        })
        messages.append({
            "role": "system",
            "content": f"Original question: {state['question']}\nPrevious simple SQL query: {state['sql_query']}\nResult: {state.get('result')}"
        })
        messages.append({
            "role": "user",
            "content": "Please provide a more complex version of the above SQL query, ensuring it adheres to the original prompt."
        })
        response = llm.invoke(messages)
        complex_sql_query = response.content.strip() if hasattr(response, "content") else response.strip()

        # Append the complex query generation to reasoning.
        state["intermediate_reasoning"].append(f"[Complex Query Generated] {complex_sql_query}")

        new_history = state.get("history", []) + [
            {"role": "user", "content": "Please provide a more complex version of the above SQL query."},
            {"role": "assistant", "content": complex_sql_query}
        ]
        
        output_state = {
            "sql_query": complex_sql_query,
            "history": new_history,
            "question": state["question"],
            "retries": state["retries"],
            "result": None,
            "complexity_stage": "complex",
            "explanation": state.get("explanation"),
            "intermediate_reasoning": state["intermediate_reasoning"]
        }
        logging.info(f"complexify_query: Output State: {output_state}")
        return output_state

    def explain_action(state: QueryState) -> QueryState:
        logging.info(f"explain_action: Input State: {state}")
        # Gather context information for explanation.
        explanation_prompt = (
            f"Explain step-by-step what actions you took to answer the following question:\n\n"
            f"Question: {state['question']}\n\n"
            f"Final SQL Query: {state['sql_query']}\n\n"
            f"Result: {state.get('result')}\n\n"
            f"Retries: {state['retries']}\n\n"
            f"Complexity Stage: {state['complexity_stage']}\n\n"
            f"Provide a clear explanation of how you generated and refined the query."
        )
        messages = [
            {"role": "system", "content": "You are an expert that explains the reasoning behind SQL query generation."},
            {"role": "user", "content": explanation_prompt}
        ]
        response = explanation_llm.invoke(messages)
        explanation_text = response.content.strip() if hasattr(response, "content") else response.strip()

        state["intermediate_reasoning"].append(f"[Final Explanation Provided] {explanation_text}")

        new_history = state.get("history", []) + [
            {"role": "assistant", "content": f"Explanation: {explanation_text}"}
        ]
        output_state = {
            **state,
            "explanation": explanation_text,
            "history": new_history,
            "intermediate_reasoning": state["intermediate_reasoning"]
        }
        logging.info(f"explain_action: Output State: {output_state}")
        return output_state

    def next_node_decision(state: QueryState) -> str:
        logging.info(f"next_node_decision: Evaluating state: {state}")
        result = state.get("result", {})
        has_error = "error" in result
        is_empty = (result.get("columns") == [] and result.get("data") == [])
        # If there's an error or empty result and retries are under 5, retry.
        if (has_error or is_empty) and state["retries"] < 5:
            return "prepare_retry"
        # If we're in the simple stage and got a valid result, move to complexify.
        if state.get("complexity_stage", "simple") == "simple" and not has_error and not is_empty:
            return "complexify_query"
        # Otherwise, end the cycle by providing an explanation.
        return "explain_action"

    graph = StateGraph(QueryState)
    graph.add_node("generate_query", generate_query)
    graph.add_node("execute_query", execute_query)
    graph.add_node("prepare_retry", prepare_retry)
    graph.add_node("complexify_query", complexify_query)
    graph.add_node("explain_action", explain_action)

    graph.set_entry_point("generate_query")
    graph.add_edge("generate_query", "execute_query")
    graph.add_conditional_edges(
        "execute_query",
        next_node_decision,
        {
            "prepare_retry": "prepare_retry",
            "complexify_query": "complexify_query",
            "explain_action": "explain_action"
        }
    )
    # After complexifying the query, execute it.
    graph.add_edge("complexify_query", "execute_query")
    # After a retry, generate a new query.
    graph.add_edge("prepare_retry", "generate_query")
    # After explanation, end the graph.
    graph.add_edge("explain_action", END)
    return graph.compile()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)  # Enable logging
    app.run(debug=True)
