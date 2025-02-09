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
import logging

load_dotenv()

app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'db'}
HISTORY_WINDOW_SIZE = 10

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# llm = ChatGoogleGenerativeAI(model="models/gemini-2.0-flash", google_api_key=os.getenv("GOOGLE_API_KEY"), temperature=0)
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

db = None
sample_data = None
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
SELECT * FROM data WHERE Year = 2024 AND Month IN ('October', 'November', 'December') LIMIT 5;
"""
    },
    {
        "input": "inflation summary for year 2024 by months",
        "answer": """
SELECT Month, AVG(Inflation (%)) AS Total Inflation (%)
FROM data
WHERE Year = 2024
GROUP BY Month
ORDER BY
    CASE
        WHEN Month = 'January' THEN 1
        WHEN Month = 'February' THEN 2
        WHEN Month = 'March' THEN 3
        WHEN Month = 'April' THEN 4
        WHEN Month = 'May' THEN 5
        WHEN Month = 'June' THEN 6
        WHEN Month = 'July' THEN 7
        WHEN Month = 'August' THEN 8
        WHEN Month = 'September' THEN 9
        WHEN Month = 'October' THEN 10
        WHEN Month = 'November' THEN 11
        WHEN Month = 'December' THEN 12
    END
"""
    },
    {
        "input": "show data for andhra, tn, up in october 2024",
        "answer": """
SELECT * FROM data
WHERE Year = 2024
AND Month = 'October'
AND State IN ('Andhra Pradesh', 'Tamil Nadu', 'Uttar Pradesh')
LIMIT 5;
"""
    },
     {
        "input": "compare sector-wise inflation",
        "answer": """
SELECT
    Year,
    AVG(CASE WHEN Sector = 'Rural' THEN Inflation (%) END) AS Rural Inflation (%),
    AVG(CASE WHEN Sector = 'Urban' THEN Inflation (%) END) AS Urban Inflation (%),
    AVG(CASE WHEN Sector = 'Combined' THEN Inflation (%) END) AS Combined Inflation (%)
FROM data
WHERE Sector IN ('rural', 'urban')
GROUP BY Year
ORDER BY Year
"""
    },
    {
        "input": "compare food and fuel inflation in combined sector",
        "answer": """
SELECT
    Year,
    AVG(CASE WHEN Group = 'Food and Beverages' THEN Inflation (%) END) AS Food Inflation (%),
    AVG(CASE WHEN Group = 'Fuel and Light' THEN Inflation (%) END) AS Fuel Inflation (%)
FROM data
WHERE Sector = 'combined' AND Group IN ('Food and Beverages', 'Fuel and Light')
GROUP BY Year
ORDER BY Year
"""
    },
    {
        "input": "show inflation rate trends in 2024",
        "answer": """
SELECT Month, AVG(Inflation (%)) AS Avg_Inflation
FROM data
WHERE Year = 2024
GROUP BY Month
ORDER BY
    CASE
        WHEN Month = 'January' THEN 1
        WHEN Month = 'February' THEN 2
        WHEN Month = 'March' THEN 3
        WHEN Month = 'April' THEN 4
        WHEN Month = 'May' THEN 5
        WHEN Month = 'June' THEN 6
        WHEN Month = 'July' THEN 7
        WHEN Month = 'August' THEN 8
        WHEN Month = 'September' THEN 9
        WHEN Month = 'October' THEN 10
        WHEN Month = 'November' THEN 11
        WHEN Month = 'December' THEN 12
    END
"""
    },{
        "input": "what factors are affecting inflation rate of Karnataka in 2024",
        "answer": """
SELECT SubGroup, AVG(Inflation (%)) AS Avg_Inflation
FROM data
WHERE Year = 2024
  AND State = 'Karnataka'
GROUP BY SubGroup
ORDER BY Avg_Inflation DESC
LIMIT 5;
"""
    },
    {
        "input": "Which three subgroups had the most volatile inflation in the last three years?",
        "answer": """SELECT SubGroup,
       SQRT(AVG(Inflation (%) * Inflation (%)) - AVG(Inflation (%)) * AVG(Inflation (%))) AS Inflation_Volatility
FROM data
WHERE Year >= (SELECT MAX(Year) FROM data) - 2
GROUP BY SubGroup
ORDER BY Inflation_Volatility DESC
LIMIT 3;
"""
    },
    {
    "input": "What is the correlation between index and inflation for each sector?",
    "answer": """
SELECT Sector,
       (SUM(Index * Inflation (%)) - SUM(Index) * SUM(Inflation (%)) / COUNT(*)) /
       (SQRT(SUM(Index * Index) - SUM(Index) * SUM(Index) / COUNT(*)) *
        SQRT(SUM(Inflation (%) * Inflation (%)) - SUM(Inflation (%)) * SUM(Inflation (%)) / COUNT(*))
       ) AS Correlation
FROM data
GROUP BY Sector
ORDER BY Correlation DESC;
"""
    }, 
    {
        "input": "Show the year-over-year inflation change for each state from 2015 to 2020",
        "answer": """
WITH YearlyAvg AS (
  SELECT State, Year, AVG([Inflation (%)]) AS AvgInflation
  FROM data
  WHERE Year BETWEEN 2014 AND 2020
  GROUP BY State, Year
),
YearlyDiff AS (
  SELECT State, Year, AvgInflation - LAG(AvgInflation) OVER (PARTITION BY State ORDER BY Year) AS YoY_Change
  FROM YearlyAvg
)
SELECT
  State,
  MAX(CASE WHEN Year = 2015 THEN YoY_Change END) AS [2015],
  MAX(CASE WHEN Year = 2016 THEN YoY_Change END) AS [2016],
  MAX(CASE WHEN Year = 2017 THEN YoY_Change END) AS [2017],
  MAX(CASE WHEN Year = 2018 THEN YoY_Change END) AS [2018],
  MAX(CASE WHEN Year = 2019 THEN YoY_Change END) AS [2019],
  MAX(CASE WHEN Year = 2020 THEN YoY_Change END) AS [2020]
FROM YearlyDiff
WHERE Year BETWEEN 2015 AND 2020
GROUP BY State;
"""
    }
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
- If the question asks about trends over time (e.g., monthly, quarterly), group by the Month column.
- If the question asks about factors affecting inflation or trends, consider aggregating on Inflation (%) and selecting columns such as State, Sector, or Group when relevant.

Generate SQL queries for SQLite following these rules:
1. Return a single SQL query per question.
2. Select necessary columns to support user question.
3. Check previous questions in the conversation history to provide context.
4. Use only existing columns from {table_info}.
5. Escape reserved keywords with backticks ().
6. Return only the SQL query without Markdown (dont wrap with
sql).
7. Use `LIMIT {top_k}` when results need to be restricted.

Available tables:
{table_info}

Here are some sample rows from the database to understand the structure:
{sample_data}

Examples:
""",
    suffix="""
Current question: {input}
SQLQuery:""",
    input_variables=["history", "input", "table_info", "top_k", "sample_data"]
)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/api/upload', methods=['POST'])
def upload_file():
    global db
    global sample_data
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

    state = {
        "question": question,
        "history": history,
        "sql_query": "",
        "sample_data": sample_data,
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
        logging.info(f"generate_query: Input State: {state}")
        chain = create_history_aware_sql_chain()
        response = chain.invoke({
            "question": state["question"],
            "history": state.get("history", []),
            "table_info": db.get_table_info(),
            "sample_data": sample_data,
            "top_k": 5
        })
        output_state = {
            "sql_query": response.strip(),
            "history": state["history"] + [state["question"]],
            "question": state["question"],
            "retries": state.get("retries", 0)
        }
        logging.info(f"generate_query: Output State: {output_state}")
        return output_state

    def execute_query(state):
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

    def prepare_retry(state):
        logging.info(f"prepare_retry: Input State: {state}")
        new_retries = state["retries"] + 1
        error_message = state["result"].get("error", "Unknown error")
        new_history = state["history"] + [
            f"Previous SQL error: {error_message}"
        ]
        output_state = {
            **state,
            "retries": new_retries,
            "history": new_history
        }
        logging.info(f"prepare_retry: Output State: {output_state}")
        return output_state

    def should_retry(state):
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

def create_history_aware_sql_chain():
    base_chain = create_sql_query_chain(
        llm=llm,
        db=db,
        prompt=PROMPT,
        k=5
    )

    return RunnablePassthrough.assign(
        history=lambda x: "\n".join(
            x.get("history", [])
        ),
        input=lambda x: x["question"],
        table_info=lambda x: db.get_table_info(),
        top_k=lambda x: 5
    ) | base_chain

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO) # Enable logging
    app.run(debug=True)