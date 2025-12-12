import streamlit as st
import ollama
import json
import subprocess
import os
import sys

# --- Configuration ---
# Get Ollama host from Docker environment variable, default to localhost if running outside Docker
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = "mistral:7b" # Or "mistral", "qwen2.5-coder"

# Define the Database Schema for the LLM
# In a full MCP implementation, this would be fetched dynamically via resources/list
DB_SCHEMA = """
Table: transactions
Columns:
- id (text): Unique transaction ID (e.g., tx_123)
- amount_cents (integer): Amount in lowest currency unit (e.g., 100 = 1.00)
- currency (text): USD, EUR, GBP
- status (text): succeeded, failed, pending, refunded
- payment_method (text): card, paypal, sofort, ideal
- country_code (text): 2-letter ISO code (US, DE, FR)
- created_at (datetime): Timestamp of transaction
"""

SYSTEM_PROMPT = f"""
You are a helpful Data Analyst. You have access to a local SQLite database.
Here is the schema:
{DB_SCHEMA}

RULES:
1. To answer the user, you must generate a SQL query.
2. Output ONLY a JSON object with the tool call. Do not output chat text yet.
3. The format must be: {{ "tool": "query_database", "sql": "SELECT..." }}
4. Always convert cents to main currency units in your final answer, but use cents in SQL.
5. For date queries, use SQLite syntax: date('now', '-1 day'), date('now', '-30 days'), etc.
6. Use only ASCII operators: >= (not ≥), <= (not ≤), = (not ==)
7. Do NOT include any markdown, code blocks, or explanations. Only JSON.
"""

# --- MCP Client Helper ---
def call_mcp_tool(sql_query):
    """
    Acts as the 'Host'. It spawns the server process, sends a JSON-RPC request,
    and returns the result.
    """
    # 1. Prepare the initialization request (REQUIRED FIRST)
    init_request = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "streamlit-analyst", "version": "1.0"}
        },
        "id": 1
    }
    
    # 2. Prepare the tool call request
    tool_request = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "query_database",
            "arguments": {"sql": sql_query}
        },
        "id": 2
    }

    try:
        process = subprocess.Popen(
            [sys.executable, "server.py"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )

        # Send both requests (init first, then tool call)
        combined_input = json.dumps(init_request) + "\n" + json.dumps(tool_request) + "\n"
        stdout, stderr = process.communicate(input=combined_input)

        if stderr:
            print(f"Server Log: {stderr}")

        # Parse responses (skip init response, use tool response)
        lines = stdout.strip().split('\n')
        if len(lines) < 2:
            return "MCP Error: Invalid server response"
        
        # The second response is our tool result
        response = json.loads(lines[1])
        
        if "error" in response:
            return f"Database Error: {response['error']['message']}"
        
        # Extract the text content from the MCP result structure
        content = response["result"]["content"][0]["text"]
        return content

    except Exception as e:
        return f"MCP Connection Error: {str(e)}"

# --- Streamlit UI ---
st.set_page_config(page_title="Local AI Analyst", page_icon="📊")

st.title("📊 Pocket Analyst (MCP + SQLite)")
st.markdown("Ask questions about your **local transaction data**. No data leaves this container.")

# Sidebar for Settings
with st.sidebar:
    st.header("Settings")
    model_id = st.text_input("Ollama Model", DEFAULT_MODEL)
    st.info(f"Connecting to: {OLLAMA_HOST}")
    if st.button("Clear Chat"):
        st.session_state.messages = []
        st.rerun()

# Initialize Chat History
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display Chat History
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- Main Logic Loop ---
if prompt := st.chat_input("Ex: How many failed payments in Germany yesterday?"):
    # 1. Display User Message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. Call LLM (First Pass - Planning)
    client = ollama.Client(host=OLLAMA_HOST)
    
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("🤔 *Thinking...*")
        
        try:
            # Send context + user prompt to Ollama
            response = client.chat(
                model=model_id,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                format="json" # Force JSON mode for better tool calling
            )
            
            llm_response_text = response['message']['content']
            
            # 3. Check if LLM wants to use a tool
            try:
                # Clean up potential markdown code blocks ```json ... ```
                cleaned_json = llm_response_text.strip().replace("```json", "").replace("```", "")
                tool_call = json.loads(cleaned_json)
            except json.JSONDecodeError:
                # If it's not JSON, the model probably just chatted (or failed)
                tool_call = None

            final_answer = ""
            
            if tool_call and tool_call.get("tool") == "query_database":
                sql_query = tool_call.get("sql")
                
                # Update UI to show we are working
                message_placeholder.markdown(f"🛠️ *Executing SQL...*")
                
                # 4. EXECUTE THE TOOL (The MCP part)
                db_result = call_mcp_tool(sql_query)
                
                # Debug info for the user
                with st.expander("🕵️ Debug: What happened under the hood?"):
                    st.code(f"Generated SQL:\n{sql_query}", language="sql")
                    st.text(f"Raw DB Result:\n{db_result[:500]}..." if len(db_result) > 500 else db_result)

                # 5. Call LLM (Second Pass - Formatting)
                # Feed the raw data back to the LLM to summarize
                final_response = client.chat(
                    model=model_id,
                    messages=[
                        {"role": "system", "content": "You are a helpful Data Analyst. Format the database results clearly and answer the user's question in 1-2 sentences. No markdown, just plain text."},
                        {"role": "user", "content": prompt},
                        {"role": "user", "content": f"Database result: {db_result}"}
                    ]
                )
                final_answer = final_response['message']['content']

            else:
                # No tool used, just echo the response (usually an error or clarification request)
                final_answer = llm_response_text

            # Display Final Answer
            message_placeholder.markdown(final_answer)
            st.session_state.messages.append({"role": "assistant", "content": final_answer})

        except Exception as e:
            st.error(f"Error connecting to Ollama: {e}")
            st.warning("Make sure Ollama is running on your host machine!")