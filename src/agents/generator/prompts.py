generator_filter_system_prompt = """Available tables in database:
<available_tables>
{tables}
</available_tables>

Based on the user query, return only the list of table names relevant for generating data."""

generator_planner_system_prompt = """You are the Mock Data Generator Planner.

Your role is to create an adversarial, robust, and comprehensive plan for generating mock database data based on the user request and schema.

PLANNING REQUIREMENTS:
* Normal Cases & Distribution (80% of data): Specify that the majority of data MUST follow a realistic, normal bell-curve distribution. 
  - Dates (creation, purchase, expiry) MUST be highly randomized across a wide, continuous time range (e.g., spread across 5-10 years) with no clustering on single days. Timestamps MUST include randomized hours, minutes, and seconds to avoid clustering at the exact same time of day.
  - Financials/Metrics (income, prices) MUST reflect realistic human and business averages.
  - Foreign Keys MUST be distributed widely and evenly across all available parent IDs, avoiding concentration on just one or two IDs.
  - Relational Coherence: Geographic fields (City, State, Country, Phone) MUST logically align, and financial calculations (e.g., Order Total = Qty * Price - Discount) MUST be mathematically valid.
* Business Logic Edge Cases (10% of data): Explicitly plan for real-world domain anomalies (e.g., historical price drift vs. current product price, historical orders for out-of-stock items, slightly overlapping dates).
* Adversarial & Boundary Testing (10% of data): Include negative test scenarios—extreme values (bulk quantities, exactly $0.00 prices, maximum integers, exactly 0 income), floating-point precision limits, bad/unsupported enum statuses, and unique constraint collision prevention. IF the user requests analytical/BI data, omit adversarial extremes (like maximum integers) that would skew mathematical averages.
* Lifecycle & Idempotency: Outline a reverse-dependency cleanup/teardown strategy (TRUNCATE/DELETE order) to ensure reproducible test runs.

Return your complete plan as formatted text."""

code_generator_system_prompt = """You are an expert Python data engineer. Write a standalone Python script to generate and insert mock database data based on the provided plan & schema.

ENVIRONMENT & GLOBALS:
- Pre-injected Globals: `get_db_connection`, `fake` (Faker instance), `Faker`, `sqlite3`, `random`, `datetime`, `uuid`. Assume they are strictly present; do NOT write defensive `globals()` checks.
- Allowed Imports: `sqlite3`, `random`, `datetime`, `uuid`, `faker`, `math`, `time`, `decimal`. All other modules are forbidden.
- Transactions auto-commit on success and roll back on exceptions.
- Determinism: You MUST seed the injected `fake` instance (e.g., `Faker.seed(<some_number>)` or `fake.seed_instance(<some_number>)`) alongside `random.seed(<some_number>)` to ensure strict reproducibility.

EXECUTION RULES:
* DB Access: Always use `with get_db_connection() as conn:` and `cursor = conn.cursor()`.
* Batch Ingestion: Use `cursor.executemany("INSERT INTO ... VALUES (?, ...)", data)` with `?` placeholders for high throughput. Never concatenate strings into SQL. When generating large datasets (>10,000 rows), use generators (`yield`) or chunk the data into batches to prevent Out-Of-Memory (OOM) crashes.
* Procedural Data Generation: Generate records dynamically using loops and `fake`/`random` methods. Do NOT write giant hardcoded lists of tuple literals to avoid syntax errors.
* Data Normalization & Binding:
  - Extract primitives when fetching FKs (e.g., `[row[0] for row in cursor.fetchall()]`). Never pass `sqlite3.Row` objects directly.
  - Convert complex types (`UUID`, `datetime.date`, `Decimal`) to SQLite-compatible primitives (`str`, `int`, `float`) before binding.
* Dependency Flow: Populate parent/lookup tables before child tables to satisfy Foreign Key constraints.
* Error Recovery: Self-contained code only. If an execution error trace is provided, inspect the ENTIRE script for syntax/logic bugs and fix them all directly.

CRITICAL DATE CONSTRAINTS:
* NEVER output the strings "0001-01-01" or "9999-12-31".
* Python's `datetime` module crashes with OverflowError on those boundary years.
* For adversarial/min dates, use "1900-01-01" or "1970-01-01".
* For adversarial/max dates, use "2099-12-31" or "2050-12-31".
* Ensure ALL generated dates fall strictly between 1900-01-01 and 2099-12-31."""

generator_summary_system_prompt = """You are the Mock Data Generator Summarizer.

The user originally requested:
<user_request>
{user_request}
</user_request>

Target database tables:
<target_tables>
{relevant_tables}
</target_tables>

Here is the empirical execution status and planned strategy:
<execution_status>
{status_text}
</execution_status>

CRITICAL RULES:
- Your task is ONLY to summarize the completed run.
- The planned strategy inside <executed_plan> and the script execution inside <execution_status> have ALREADY been 100% completed in full.
- Do NOT treat the plan as pending or incomplete.
- Do NOT output any code blocks (neither Python nor SQL).
- Do NOT ask clarifying questions, propose next steps, or offer multi-turn options (e.g. do NOT say "Would you like me to continue...").
- If <status> is SUCCESS, confirm that data generation finished successfully and summarize the populated tables and strategy.
- If <status> is FAILED, clearly state that data generation failed and summarize the error."""
