import pandas as pd
import sqlite3


df = pd.read_csv('dataset/cpi Group data.csv')



df.replace('*', pd.NA, inplace=True)


df = df.convert_dtypes()





table_name = 'data'



custom_dtypes = {
    'BaseYear': 'int',       
    'Year': 'int',     
    'Month': 'string',
    'State': 'string', 
    'Sector': 'string',
    'Group': 'string',
    'SubGroup': 'string',
    'Index': 'float',
    'Inflation (%)': 'float'
}
sql_dtypes = {
    'int': 'INTEGER',
    'float': 'REAL',
    'string': 'TEXT',
    'datetime64': 'DATETIME'
}


df = df.astype(custom_dtypes)
conn = sqlite3.connect('database/dataset.db')
cursor = conn.cursor()

columns = ', '.join([f'"{col}" {sql_dtypes[custom_dtypes[col]]}' for col in df.columns])
create_table_sql = f'CREATE TABLE IF NOT EXISTS {table_name} ({columns})'
cursor.execute(create_table_sql)


df.to_sql(table_name, conn, if_exists='replace', index=False)


conn.commit()
conn.close()