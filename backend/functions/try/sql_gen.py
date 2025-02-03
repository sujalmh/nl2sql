from langchain_openai import ChatOpenAI
from langchain.chains import create_sql_query_chain
from langchain_community.utilities import SQLDatabase
from langchain_core.prompts import PromptTemplate
from langgraph.graph import StateGraph
import ast
from typing import Annotated, TypedDict, List, Optional
from langchain_core.runnables import RunnablePassthrough



db = SQLDatabase.from_uri("sqlite:///database/dataset.db")
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


class QueryState(TypedDict):
    question: str
    history: List[str]
    sql_query: str
    result: Optional[list]
    retries: int  

PROMPT = PromptTemplate.from_template(""" 
You are a SQL expert analyzing economic data. Use this conversation history to understand context:

{history}

Current question: {input}

Generate SQL query for the SQLite database. Only use columns that exist in the tables.
Return only SQL without Markdown formatting. Tables: {table_info}. Limit to {top_k} results per select statement.
""")

def create_history_aware_sql_chain(llm, db, prompt=PROMPT):
    base_chain = create_sql_query_chain(
        llm=llm,
        db=db,
        prompt=prompt,
        k=5
    )
    
    return RunnablePassthrough.assign(
        history=lambda x: "\n".join(x.get("history", [])),
        input=lambda x: x["question"] + "\nSQLQuery: ",
        table_info=lambda x: db.get_table_info(),  
        top_k=lambda x: 5  
    ) | base_chain

def generate_query(state):
    """Generate SQL with full context history"""
    response = create_history_aware_sql_chain(llm, db).invoke({
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
    """Executes SQL query, retries once if it fails."""
    if 'sql_query' not in state:
        raise KeyError("'sql_query' key is missing in the state")
    
    query = state["sql_query"]
    
    try:
        result = db.run(query)
        parsed_result = None
        try:
            parsed_result = ast.literal_eval(result)
        except (ValueError, SyntaxError):
            parsed_result = result
        
        return {
            "result": parsed_result,
            "history": state["history"],
            "sql_query": state["sql_query"],
            "question": state["question"],
            "retries": state["retries"]
        }

    except Exception as e:
        if state["retries"] < 1:  
            print(f"\n⚠️ SQL Execution Failed: {e}. Retrying...\n")
            state["retries"] += 1
            return generate_query(state)  
        
        print(f"\n❌ SQL Execution Failed Again: {e}. Aborting query.\n")
        return {
            "result": "Error: SQL execution failed twice.",
            "history": state["history"],
            "sql_query": state["sql_query"],
            "question": state["question"],
            "retries": state["retries"]
        }

graph = StateGraph(QueryState)

graph.add_node("generate_query", generate_query)
graph.add_node("execute_query", execute_query)

graph.set_entry_point("generate_query")
graph.add_edge("generate_query", "execute_query")

graph = graph.compile()

def cli_interface():
    print("Welcome to the SQL Query Simulation! Type 'exit' to quit.")
    state = {"history": [], "sql_query": "", "result": None, "question": "", "retries": 0}
    
    while True:
        question = input("\nEnter your question: ")
        if question.lower() == 'exit':
            break
        
        state["question"] = question
        state = graph.invoke(state)
        
        print(f"\nSQL Query: {state['sql_query']}")
        print(f"Result: {state['result']}")
        print(f"Context: {state['history'][-2:]}")  
        
        if input("\nAnother question? (yes/no): ").lower() != 'yes':
            break

cli_interface()
