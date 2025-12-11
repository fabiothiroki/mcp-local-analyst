from mcp.server.fastmcp import FastMCP
import sqlite3
import os
import json

# Initialize the MCP Server
mcp = FastMCP("PocketAnalyst")

# Configuration
DB_FOLDER = "data"
DB_NAME = "payments.db"
DB_PATH = os.path.join(DB_FOLDER, DB_NAME)

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        # This enables column access by name: row['column_name']
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to connect to database at {DB_PATH}: {e}")

@mcp.resource("sqlite://schema")
def get_schema() -> str:
    """
    Reads the database schema (table definitions) and returns it as a string.
    This provides the 'Context' for the LLM.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get all table names
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    schema_text = []
    for table in tables:
        table_name = table['name']
        # Get the CREATE statement for each table
        cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}';")
        create_stmt = cursor.fetchone()['sql']
        schema_text.append(create_stmt)
        
    conn.close()
    return "\n\n".join(schema_text)

@mcp.tool()
def query_database(sql: str) -> str:
    """
    Executes a read-only SQL query against the database.
    Args:
        sql: The SELECT statement to execute.
    """
    # 1. Security Guard: Prevent destructive commands
    if not sql.strip().upper().startswith("SELECT"):
        return "Error: For safety, this tool only allows SELECT queries."

    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 2. Execute the query
        cursor.execute(sql)
        rows = cursor.fetchall()
        
        # 3. Convert results to a list of dictionaries (easier for LLM to read)
        # This handles the transformation from SQLite objects to pure JSON-serializable data
        result_data = [dict(row) for row in rows]
        
        # 4. Return as JSON string
        # We limit the output to prevent blowing up the LLM context window
        if len(result_data) > 100:
            return json.dumps({
                "warning": "Result truncated to first 100 rows for performance.",
                "data": result_data[:100]
            }, default=str)
            
        return json.dumps(result_data, default=str)

    except sqlite3.Error as e:
        # Return the specific SQL error so the LLM can try to fix it
        return f"SQL Error: {str(e)}"
        
    finally:
        conn.close()

if __name__ == "__main__":
    # This starts the stdio server
    mcp.run()