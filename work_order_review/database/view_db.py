import sqlite3
from pathlib import Path
import json
from tabulate import tabulate  # you might need to pip install tabulate

def view_db():
    # Get database path
    db_path = Path(__file__).parent.parent.parent / "data" / "work_order_review.db"
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get list of tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    for table in tables:
        table_name = table[0]
        print(f"\n\n=== {table_name} ===")
        
        # Get all rows from table
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
        
        # Get column names
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Format the data (pretty print JSON fields)
        formatted_rows = []
        for row in rows:
            formatted_row = []
            for value in row:
                if isinstance(value, str) and value.startswith('{'):
                    try:
                        # Try to parse and pretty print JSON
                        parsed = json.loads(value)
                        formatted_row.append(json.dumps(parsed, indent=2))
                    except:
                        formatted_row.append(value)
                else:
                    formatted_row.append(value)
            formatted_rows.append(formatted_row)
        
        # Print table
        print(tabulate(formatted_rows, headers=columns, tablefmt="grid"))
        
    conn.close()

if __name__ == "__main__":
    # Make sure PYTHONPATH includes the root directory
    import sys
    from pathlib import Path
    root_dir = Path(__file__).parent.parent.parent
    sys.path.append(str(root_dir))
    
    view_db() 