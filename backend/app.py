from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from werkzeug.utils import secure_filename
from langchain_openai import ChatOpenAI
from langchain.chains import create_sql_query_chain
from langchain_community.utilities import SQLDatabase
from langchain_core.prompts import FewShotPromptTemplate, PromptTemplate
from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnablePassthrough
import ast
from typing import TypedDict, List, Optional
from sqlalchemy import text

app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'db'}
HISTORY_WINDOW_SIZE = 3

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
db = None  

class QueryState(TypedDict):
    question: str
    history: List[str]
    sql_query: str
    result: Optional[dict]
    retries: int  

examples = [
    {
        "input": "show results from oct, nov, dec 2024",
        "answer": """
SELECT * FROM `data` WHERE `Year` = 2024 AND `Month` IN ('October', 'November', 'December') LIMIT 5;
"""
    },
    {
        "input": "inflation summary for year 2024 by months",
        "answer": """
SELECT `Month`, SUM(`Inflation (%)`) AS `Total Inflation (%)`
FROM `data`
WHERE `Year` = 2024
GROUP BY `Month`
ORDER BY `Month`
LIMIT 5;
"""
    },
    {
        "input": "show data for andhra in october 2024",
        "answer": """
SELECT * FROM `data` 
WHERE `Year` = 2024 AND `Month` = 'October' AND `State` = 'Andhra Pradesh'
LIMIT 5;
"""
    },
    {
        "input": "show data for andhra, tn, up in october 2024",
        "answer": """
SELECT * FROM `data` 
WHERE `Year` = 2024 
AND `Month` = 'October' 
AND `State` IN ('Andhra Pradesh', 'Tamil Nadu', 'Uttar Pradesh') 
LIMIT 5;
"""
    },
]

example_prompt = PromptTemplate(
    input_variables=["input", "answer"],
    template="Question: {input}\nSQLQuery: {answer}"
)

PROMPT = FewShotPromptTemplate(
    examples=examples,
    example_prompt=example_prompt,
    prefix=""" 
You are a SQL expert analyzing economic data. Use this conversation history to understand context:

{history}

Generate SQL queries for SQLite following these rules:
1. Use only existing columns.
2. Escape reserved keywords with backticks (`).
3. Return only SQL without Markdown.
4. Limit results to {top_k} per SELECT.

Available tables: {table_info}

Examples:
""",
    suffix="""
Current question: {input}
SQLQuery:""",
    input_variables=["history", "input", "table_info", "top_k"]
)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/api/upload', methods=['POST'])
def upload_file():
    global db
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

    state = {
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
    def generate_query(state):
        chain = create_history_aware_sql_chain()
        response = chain.invoke({
            "question": state["question"],
            "history": state.get("history", []),
            "table_info": db.get_table_info(),
            "top_k": 5  
        })
        return {
            "sql_query": response.strip(),
            "history": state["history"] + [state["question"]],
            "question": state["question"],
            "retries": state.get("retries", 0)
        }

    def execute_query(state):
        try:
            query = state["sql_query"]
            result = {"columns": [], "data": []}

            raw_query_result = db.run(query, fetch="cursor")
            query_result = list(raw_query_result.mappings())
            
            if query_result:
                result["columns"] = list(query_result[0].keys())
                result["data"] = [dict(row) for row in query_result]
            
            return {
                "result": result,
                "history": state["history"],
                "sql_query": state["sql_query"],
                "question": state["question"],
                "retries": state["retries"]
            }
        except Exception as e:
            return {
                "result": {"error": str(e)},
                "history": state["history"],
                "sql_query": state["sql_query"],
                "question": state["question"],
                "retries": state["retries"]
            }

    def prepare_retry(state):
        new_retries = state["retries"] + 1
        error_message = state["result"].get("error", "Unknown error")
        new_history = state["history"] + [
            f"Previous SQL error: {error_message}"
        ]
        return {
            **state,
            "retries": new_retries,
            "history": new_history[-HISTORY_WINDOW_SIZE:]
        }

    def should_retry(state):
        has_error = "error" in state.get("result", {})
        retries = state.get("retries", 0)
        return has_error and retries < 1

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

def create_history_aware_sql_chain():
    base_chain = create_sql_query_chain(
        llm=llm,
        db=db,
        prompt=PROMPT,
        k=5
    )
    
    return RunnablePassthrough.assign(
        history=lambda x: "\n".join(
            x.get("history", [])[-HISTORY_WINDOW_SIZE:]
        ),
        input=lambda x: x["question"],
        table_info=lambda x: db.get_table_info(),  
        top_k=lambda x: 5  
    ) | base_chain

if __name__ == '__main__':
    app.run(debug=True)
