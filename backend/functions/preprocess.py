import pandas as pd
import sqlite3

# Read the CSV file, replacing '*' with None
df = pd.read_csv("dataset\cpi Group data.csv", sep="\t", na_values=["*"])

# Create an SQLite database
conn = sqlite3.connect("inflation_data.db")
cursor = conn.cursor()

# Create table
cursor.execute('''
CREATE TABLE IF NOT EXISTS data (
    BaseYear INTEGER,
    Year INTEGER,
    Month TEXT,
    State TEXT,
    Sector TEXT,
    "Group" TEXT,
    SubGroup TEXT,
    "Index" REAL,
    "Inflation (%)" REAL
)
''')

# Insert data into the table
df.to_sql("data", conn, if_exists="replace", index=False)

# Commit and close connection
conn.commit()
conn.close()
