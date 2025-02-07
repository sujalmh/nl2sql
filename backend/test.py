from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Initialize the model
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash-lite-preview-02-05",  # Use the specific model name you want
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    temperature=0.7,
    max_output_tokens=2048
)

# Simple query
response = llm.invoke("Explain quantum physics in simple terms")
print(response.content)