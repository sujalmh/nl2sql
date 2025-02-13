# Results

## 1. Context-Aware
![411351908-8a4bffeb-0c84-4ab8-b5e8-0c834d2a8227](https://github.com/user-attachments/assets/a6931a18-9ad3-489c-9ab2-a4c9825359fc)
![411365887-bf52a27b-d47f-4d13-99b3-054d5a805023](https://github.com/user-attachments/assets/313eec8b-2a9f-47db-a290-9ef918f575ac)
![412120426-551275e7-b5db-435b-a16d-7db977761d9f](https://github.com/user-attachments/assets/1b116d90-636b-4d07-acf3-f1a11d21c707)
To compare the results, I created a pivot table in the excel worksheet. <br>
![image](https://github.com/user-attachments/assets/d76126be-3c11-4c4c-8eee-a84bedf6a8f5) <br>
Here are the results from the excel worksheet corresponding to the output from generated SQL query:  
![Doc1_page-0001](https://github.com/user-attachments/assets/5a512059-04b4-4be3-862e-a2b81cbdd117)
![Doc1_page-0002](https://github.com/user-attachments/assets/5e48496e-62e0-4477-b6f0-e0d6492ae0da)

All the values from the original excel worksheet match with the output form generated SQL query

The context is carried throughout the question.

---
## 2. Handling Partial Entity Names in Queries
![411351995-a169d218-6267-447a-8fd0-9690396db3e0](https://github.com/user-attachments/assets/8eeb346f-1a3e-4cb3-9032-e61724466980)
To compare the results, I used the formula `=AVERAGEIFS(I:I, B:B, K2, E:E, "Rural", F:F, "Food and Beverages")` and `=AVERAGEIFS(I:I, B:B, B2, E:E, "Rural", F:F, "Fuel and Light")` in the original excel worksheet. 
`Column B = Year
Column E = Sector
Column F = Group
Column I = Inflation (%)` <br>
![image](https://github.com/user-attachments/assets/c1efdf2a-6cdc-4dad-828d-9e74065ddb0e)

When a user asks question without using the full entity name, the AI understands it and uses the full entity name to query. In the example, user asks compare food and fuel inflation in rural sector. The generated SQL uses groups `Food and Beverages` and `Fuel and Light` when not explicitly mentioned.

---
## 3. Understanding Trends
![411352249-948ddd80-b403-45e5-ab08-19f3daa3e2d6](https://github.com/user-attachments/assets/1e652eff-705f-4e50-a266-4d3fc9ae8628)
To verify the results, I created a pivot table in the excel worksheet. <br>
![image](https://github.com/user-attachments/assets/7185169d-4303-46e5-936e-17cc83e6ee9b)
All the values from the original excel worksheet match with the output form generated SQL query.

In the example, user asks show inflation rate trends in 2024. The generated SQL query returns results with average inflation rate for every month, sorted calender-wise, for better comparison. This highlights that the AI understands the intent behind "trends" and structures the SQL query accordingly.

---
## 4. Identifying Key Factors
![what-factors-are-affecting-inflation-rate-of-maharashtra-in-2024](https://github.com/user-attachments/assets/b3cfeb75-347e-4a58-aeec-b5323254e840)
To verify the results, I created a pivot table in the excel worksheet. <br>
![image](https://github.com/user-attachments/assets/bdbb96ce-ce53-44db-9698-f254545d8ee5)
All the values from the original excel worksheet match with the output form generated SQL query.

The user asks what factors are affecting the inflation rate. The generated SQL query returns results with average inflation for each subgroup showing which subgroup is affecting the inflation rate most. This highlights that the AI understands the intent and retrieves subgroup-level insights to explain inflation trends.

---
## 5. Year-over-Year Inflation
![411352407-4d547650-4e32-4336-a82d-294e668ab6e3](https://github.com/user-attachments/assets/afe3dcdf-dd4d-4250-a6a6-f4a99d624af4)
![image](https://github.com/user-attachments/assets/22d17ba9-8490-4a51-84bf-c729a8538dbd)

The user asks for year-over-year difference in inflation rate for every state. The generated SQL is complex which takes average for each year and then subtracts with the year preceeding it. The SQL results are also formatted in a user-friendly way to help compare easily.

---
## 6. Identifying Inflation Volatility (Statistical Analysis)
![volatility](https://github.com/user-attachments/assets/86686eae-a7ad-4e5a-9667-05046a51eafd)
To verify the results, I created a pivot table in the excel worksheet. <br>
![image](https://github.com/user-attachments/assets/c39a78df-97c1-48a2-9fb8-b6063a409a3f)
Values over the years 2021-2014 is considered, then the standard deviation of the inflation rate % is taken over those years.

The user asks for most volatile inflation. The generated SQL uses standard deviation to compare the inflation rates between subgroups. This uses mathematical queries to get meaningful results.

---
## 7. Analyzing Correlation (Statistical Analysis)
![correlation](https://github.com/user-attachments/assets/a9202c3c-c699-4c2d-8568-d4ff84ca9296)

This example shows the SQL query using mathematical query for correlation between Index and Inflation rate, allowing easier understanding of the data.

---
## 8. Implementing SQL Query Retry Mechanism for Robust Execution
![retry](https://github.com/user-attachments/assets/b0a96e4d-838f-485b-bef6-0c234ec1c3d2)

Error log:
```
INFO:root:prepare_retry: Input State: {'question': 'for food', 'history': ['show data', 'for food'], 'sql_query': "SELECT * FROM data WHERE Group = 'Food and Beverages' LIMIT 5;", 'result': {'error': '(sqlite3.OperationalError) near "Group": syntax error\n[SQL: SELECT * FROM data WHERE Group = \'Food and Beverages\' LIMIT 5;]\n(Background on this error at: https://sqlalche.me/e/20/e3q8)'}, 'retries': 0}
INFO:root:prepare_retry: Output State: {'question': 'for food', 'history': ['show data', 'for food', 'Previous SQL error: (sqlite3.OperationalError) near "Group": syntax error\n[SQL: SELECT * FROM data WHERE Group = \'Food and Beverages\' LIMIT 5;]\n(Background on this error at: https://sqlalche.me/e/20/e3q8)'], 'sql_query': "SELECT * FROM data WHERE Group = 'Food and Beverages' LIMIT 5;", 'result': {'error': '(sqlite3.OperationalError) near "Group": syntax error\n[SQL: SELECT * FROM data WHERE Group = \'Food and Beverages\' LIMIT 5;]\n(Background on this error at: https://sqlalche.me/e/20/e3q8)'}, 'retries': 1}
INFO:root:generate_query: Input State: {'question': 'for food', 'history': ['show data', 'for food', 'Previous SQL error: (sqlite3.OperationalError) near "Group": syntax error\n[SQL: SELECT * FROM data WHERE Group = \'Food and Beverages\' LIMIT 5;]\n(Background on this error at: https://sqlalche.me/e/20/e3q8)'], 'sql_query': "SELECT * FROM data WHERE Group = 'Food and Beverages' LIMIT 5;", 'result': {'error': '(sqlite3.OperationalError) near "Group": syntax error\n[SQL: SELECT * FROM data WHERE Group = \'Food and Beverages\' LIMIT 5;]\n(Background on this error at: https://sqlalche.me/e/20/e3q8)'}, 'retries': 1}
INFO:httpx:HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
INFO:root:generate_query: Output State: {'sql_query': 'SELECT * FROM data WHERE "Group" = \'Food and Beverages\' LIMIT 5;', 'history': ['shiw data', 'for food', 'Previous SQL error: (sqlite3.OperationalError) near "Group": syntax error\n[SQL: SELECT * FROM data WHERE Group = \'Food and Beverages\' LIMIT 5;]\n(Background on this error at: https://sqlalche.me/e/20/e3q8)', 'for food'], 'question': 'for food', 'retries': 1}
INFO:root:execute_query: Input State: {'question': 'for food', 'history': ['show data', 'for food', 'Previous SQL error: (sqlite3.OperationalError) near "Group": syntax error\n[SQL: SELECT * FROM data WHERE Group = \'Food and Beverages\' LIMIT 5;]\n(Background on this error at: https://sqlalche.me/e/20/e3q8)', 'for food'], 'sql_query': 'SELECT * FROM data WHERE "Group" = \'Food and Beverages\' LIMIT 5;', 'result': {'error': '(sqlite3.OperationalError) near "Group": syntax error\n[SQL: SELECT * FROM data WHERE Group = \'Food and Beverages\' LIMIT 5;]\n(Background on this error at: https://sqlalche.me/e/20/e3q8)'}, 'retries': 1}
INFO:root:execute_query: Output State: {'result': {'columns': ['BaseYear', 'Year', 'Month', 'State', 'Sector', 'Group', 'SubGroup', 'Index', 'Inflation (%)'], 'data': [{'BaseYear': 2012, 'Year': 2024, 'Month': 'December', 'State': 'All India', 'Sector': 'Combined', 'Group': 'Food and Beverages', 'SubGroup': 'Cereals and Products', 'Index': 198.1, 'Inflation (%)': 6.51}, {'BaseYear': 2012, 'Year': 2024, 'Month': 'December', 'State': 'All India', 'Sector': 'Combined', 'Group': 'Food and Beverages', 'SubGroup': 'Meat and Fish', 'Index': 222.5, 'Inflation (%)': 5.3}, {'BaseYear': 2012, 'Year': 2024, 'Month': 'December', 'State': 'All India', 'Sector': 'Combined', 'Group': 'Food and Beverages', 'SubGroup': 'Egg', 'Index': 212.1, 'Inflation (%)': 6.85}, {'BaseYear': 2012, 'Year': 2024, 'Month': 'December', 'State': 'All India', 'Sector': 'Combined', 'Group': 'Food and Beverages', 'SubGroup': 'Milk and Products', 'Index': 187.5, 'Inflation (%)': 2.8}, {'BaseYear': 2012, 'Year': 2024, 'Month': 'December', 'State': 'All India', 'Sector': 'Combined', 'Group': 'Food and Beverages', 'SubGroup': 'Oils and Fats', 'Index': 183.7, 'Inflation (%)': 14.6}]}, 'history': ['show data', 'for food', 'Previous SQL error: (sqlite3.OperationalError) near "Group": syntax error\n[SQL: SELECT * FROM data WHERE Group = \'Food and Beverages\' LIMIT 5;]\n(Background on this error at: https://sqlalche.me/e/20/e3q8)', 'for food'], 'sql_query': 'SELECT * FROM data WHERE "Group" = \'Food and Beverages\' LIMIT 5;', 'question': 'for food', 'retries': 1}
```
This example shows the retry process included in the code. When an error is encountered during execution of a SQL Query, retry is triggered. The retry process includes passing the error along with the question again, it is repeated 3 times in case of en error. This will ensure less errors are occurred during execution, hence giving accurate results.

---

