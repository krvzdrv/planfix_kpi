import psycopg2
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

try:
    # Connect to database
    conn = psycopg2.connect(
        host=os.environ.get('SUPABASE_HOST'),
        dbname=os.environ.get('SUPABASE_DB'),
        user=os.environ.get('SUPABASE_USER'),
        password=os.environ.get('SUPABASE_PASSWORD'),
        port=os.environ.get('SUPABASE_PORT')
    )
    
    cur = conn.cursor()
    
    # Check table structure
    cur.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'kpi_metrics' 
        ORDER BY ordinal_position
    """)
    
    print("Columns in kpi_metrics table:")
    for row in cur.fetchall():
        print(f"  {row[0]} ({row[1]})")
    
    # Check if msp column exists
    cur.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'kpi_metrics' AND column_name = 'msp'
    """)
    
    msp_exists = cur.fetchone()
    if msp_exists:
        print("\n✅ Column 'msp' exists in kpi_metrics table")
    else:
        print("\n❌ Column 'msp' does NOT exist in kpi_metrics table")
        print("You need to add this column to the database")
    
    conn.close()
    
except Exception as e:
    print(f"Error: {e}") 