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
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv
import os
load_dotenv()

app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'db'}
HISTORY_WINDOW_SIZE = 10

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# llm = ChatGoogleGenerativeAI(model="models/gemini-2.0-flash-lite-preview-02-05", google_api_key=os.getenv("GOOGLE_API_KEY"), temperature=0)
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
SELECT `Month`, AVG(`Inflation (%)`) AS `Total Inflation (%)`
FROM `data`
WHERE `Year` = 2024
GROUP BY `Month`
ORDER BY 
    CASE 
        WHEN `Month` = 'January' THEN 1
        WHEN `Month` = 'February' THEN 2
        WHEN `Month` = 'March' THEN 3
        WHEN `Month` = 'April' THEN 4
        WHEN `Month` = 'May' THEN 5
        WHEN `Month` = 'June' THEN 6
        WHEN `Month` = 'July' THEN 7
        WHEN `Month` = 'August' THEN 8
        WHEN `Month` = 'September' THEN 9
        WHEN `Month` = 'October' THEN 10
        WHEN `Month` = 'November' THEN 11
        WHEN `Month` = 'December' THEN 12
    END
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
     {
        "input": "compare sector-wise inflation",
        "answer": """
SELECT
    `Year`,
    AVG(CASE WHEN Sector = 'Rural' THEN `Inflation (%)` END) AS `Rural Inflation (%)`,
    AVG(CASE WHEN Sector = 'Urban' THEN `Inflation (%)` END) AS `Urban Inflation (%)`,
    AVG(CASE WHEN Sector = 'Combined' THEN `Inflation (%)` END) AS `Combined Inflation (%)`
FROM `data`
WHERE Sector IN ('rural', 'urban')
GROUP BY `Year`
ORDER BY `Year`
"""
    },
    {
        "input": "compare food and fuel inflation in combined sector",
        "answer": """
SELECT
    `Year`,
    AVG(CASE WHEN `Group` = 'Food and Beverages' THEN `Inflation (%)` END) AS `Food Inflation (%)`,
    AVG(CASE WHEN `Group` = 'Fuel and Light' THEN `Inflation (%)` END) AS `Fuel Inflation (%)`
FROM `data`
WHERE Sector = 'combined' AND `Group` IN ('Food and Beverages', 'Fuel and Light')
GROUP BY `Year`
ORDER BY `Year`
"""
    },
    {
        "input": "show inflation rate trends in 2024",
        "answer": """
SELECT `Month`, AVG(`Inflation (%)`) AS `Avg_Inflation`
FROM `data`
WHERE `Year` = 2024
GROUP BY `Month`
ORDER BY 
    CASE 
        WHEN `Month` = 'January' THEN 1
        WHEN `Month` = 'February' THEN 2
        WHEN `Month` = 'March' THEN 3
        WHEN `Month` = 'April' THEN 4
        WHEN `Month` = 'May' THEN 5
        WHEN `Month` = 'June' THEN 6
        WHEN `Month` = 'July' THEN 7
        WHEN `Month` = 'August' THEN 8
        WHEN `Month` = 'September' THEN 9
        WHEN `Month` = 'October' THEN 10
        WHEN `Month` = 'November' THEN 11
        WHEN `Month` = 'December' THEN 12
    END
"""
    },{
        "input": "what factors are affecting inflation rate of Karnataka in 2024",
        "answer": """
SELECT `SubGroup`, AVG(`Inflation (%)`) AS `Avg_Inflation`
FROM `data`
WHERE `Year` = 2024 
  AND `State` = 'Karnataka'
GROUP BY `SubGroup`,
ORDER BY `Avg_Inflation` DESC
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
You are a SQL expert analyzing economic data, helping normal users use NL to query data. Use this conversation history to understand context:

{history}

When the question is vague or requires summarization:
- Identify and select only the columns relevant to the question.
- Use appropriate aggregations (e.g., SUM, AVG, COUNT) or grouping when the question asks for trends or summaries.
- If the question asks about trends over time (e.g., monthly, quarterly), group by the `Month` column.
- If the question asks about factors affecting inflation or trends, consider aggregating on `Inflation (%)` and selecting columns such as `State`, `Sector`, or `Group` when relevant.

Generate SQL queries for SQLite following these rules:
1. Return single sql query per question.
2. Return required columns relevant to the question. 
2. Use only existing columns.
3. Escape reserved keywords with backticks (`).
4. Return only SQL without Markdown.
5. Limit results to {top_k} per SELECT, or show full results only when relevant.

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
