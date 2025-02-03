from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START
from langchain_core.messages import HumanMessage, AIMessage
import uuid


# 1. Connect to the SQL database
db = SQLDatabase.from_uri("sqlite:///database/dataset.db")

# 2. Initialize the language model
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# 3. Define state schema with messages and additional context
# 3. Define state schema with messages and additional context
class SQLGenerationState(dict):
    @property
    def messages(self):
        return self.get("messages", [])
    
    @property
    def table_info(self):
        return self.get("table_info", db.get_table_info())

# 4. Define custom prompt template
custom_prompt = PromptTemplate(
    input_variables=["input", "table_info", "messages"],
    template="""
Previous Interactions:
{messages}

Based on the following database schema, write a SQL query to answer the question:

Schema Information:
{table_info}

Question: {input}

SQLQuery:"""
)

# 5. Create the SQL generation chain
def generate_sql_query(state: SQLGenerationState):
    # Prepare the input for the prompt
    prompt_input = {
        "input": state["input"],
        "table_info": state["table_info"],
        "messages": "\n".join([f"{m.type}: {m.content}" for m in state["messages"] if m.type in ["human", "ai"]])
    }
    
    # Generate the SQL query
    sql_query = custom_prompt | llm | RunnableLambda(lambda x: x.content)
    result = sql_query.invoke(prompt_input)
    
    # Update the state with the new message
    state["messages"].append(AIMessage(content=result))
    return state

# 6. Set up LangGraph workflow
workflow = StateGraph(state_schema=SQLGenerationState)

# Add the SQL generation node
workflow.add_node("sql_generator", generate_sql_query)

# Define the workflow edges
workflow.add_edge(START, "sql_generator")
workflow.add_edge("sql_generator", "sql_generator")  # Allow follow-up questions

# Set the entry point
workflow.set_entry_point("sql_generator")

# 7. Configure memory with checkpointing
memory = MemorySaver()
app = workflow.compile(checkpointer=memory)

# 8. Create conversation manager
class SQLConversationManager:
    def __init__(self):
        self.threads = {}
    
    def new_thread(self):
        thread_id = str(uuid.uuid4())
        self.threads[thread_id] = {"config": {"configurable": {"thread_id": thread_id}}}
        return thread_id
    
    def ask_question(self, thread_id, question):
        config = self.threads[thread_id]["config"]
        
        # Initialize or update the state
        state = {
            "input": question,
            "messages": [HumanMessage(content=question)],
            "table_info": db.get_table_info()
        }
        
        # Stream the response
        for event in app.stream(state, config, stream_mode="values"):
            if "messages" in event:
                return event["messages"][-1].content

# Example Usage
if __name__ == "__main__":
    manager = SQLConversationManager()
    thread_id = manager.new_thread()

    # First question
    question1 = "How many records in october 2024?"
    response1 = manager.ask_question(thread_id, question1)
    print(f"Question 1: {question1}\nSQL Query 1: {response1}\n")

    # Follow-up question using context
    question2 = "What is the average of that month?"
    response2 = manager.ask_question(thread_id, question2)
    print(f"Question 2: {question2}\nSQL Query 2: {response2}")