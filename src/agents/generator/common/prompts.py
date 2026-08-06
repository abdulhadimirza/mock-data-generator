generator_infer_system_prompt = """Based on the user request, classify the primary intent of the mock data generation:
- "Stress Testing": The user wants edge cases, adversarial values, boundary testing, stress testing, negative test cases, or QA robustness testing.
- "Realistic Analytics": The user wants clean, realistic, statistically sound data for BI dashboards, reporting, visualization, or standard business analytics without extreme mathematical anomalies.

Select the most appropriate generation mode."""

generator_filter_system_prompt = """Available tables in database:
<available_tables>
{tables}
</available_tables>

Based on the user query, return only the list of table names relevant for generating data."""

generator_summary_system_prompt = """<role>
You are the Mock Data Generator Summarizer.
</role>

The user originally requested:
<user_request>
{user_request}
</user_request>

Target database tables:
<target_tables>
{relevant_tables}
</target_tables>

Planned Strategy:
<executed_plan>
{executed_plan}
</executed_plan>

Empirical Execution Status & Output:
<execution_status>
{execution_status}
</execution_status>

<critical_rules>
- Your task is strictly to summarize the completed run.
- Treat the planned strategy inside <executed_plan> and the script execution output inside <execution_status> as already executed.
- Provide your response without any code blocks (neither Python nor SQL).
- Conclude directly with the summary, omitting clarifying questions, proposed next steps, or multi-turn options.
- If status inside <execution_status> is SUCCESS, summarize the populated tables and data strategy.
- If status inside <execution_status> is FAILED, state that data generation failed and summarize the error.
</critical_rules>"""

BASE_PLANNER_REQUIREMENTS = """  <requirement name="normal_cases_and_distribution">
    Normal Cases & Distribution ({normal_pct}% of data): The majority of data MUST follow a realistic, normal bell-curve distribution.
    - Temporal Realism: Apply weighted, non-uniform date distributions. Implement domain-appropriate volume curves, such as Year-over-Year (YoY) growth and seasonality/time-of-day clustering (e.g., business hours for B2B, evening spikes for social, seasonal spikes for retail).
    - Dates: Randomize creation, purchase, and expiry dates across a continuous time range, ensuring a smooth spread across days. Timestamps MUST include randomized hours/minutes/seconds.
    - Metrics & Measurements: Scale financials, usage stats, and physical measurements to realistic human, system, or business averages.
    - Categorical Realism: Restrict categories, statuses, locations, and roles strictly to domain-appropriate values (e.g., enforce localized geographic or specific industry constraints implied by the schema). 
    - Foreign Keys: Distribute relationships widely and evenly across the available parent ID pool, unless a power-law/Pareto distribution (80/20 rule) aligns better with the specific domain.
    - Relational Coherence: Ensure logical alignment for geographic fields (City/State/Country/Zip) and mathematical validity for domain-specific formulas (e.g., `Total = Qty * Price`, `Duration = End - Start`).
    - Procedural Generation: Use procedural generation for all names, locations, and categorical entities. Instruct the code generator to dynamically synthesize text fields using the Faker library and loops to guarantee script stability.
  </requirement>

  <requirement name="business_logic_edge_cases">
    Business Logic Edge Cases (10% of data): Plan explicitly for real-world domain anomalies (e.g., inactive users with recent activity, historical records for inactive entities, slightly overlapping schedules, or parent records with zero children).
    - Historical Drift & Entity Consistency: For metrics evolving over time (e.g., prices, subscription tiers, health metrics), map ~80% of transactional records to the current state. Map the remaining ~20% to represent historical drift, ensuring older records logically correlate with older baseline averages on the timeline.
  </requirement>
"""
