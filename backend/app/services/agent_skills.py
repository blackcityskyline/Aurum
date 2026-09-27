"""Agent skills — specialized instructions for financial analysis.

These skills guide the agent's behavior when analyzing transactions,
processing files, and supporting the user. They are injected into the
system prompt to help the model provide better assistance.
"""

TRANSACTION_ANALYSIS_SKILL = """
## Transaction Analysis Skill

When analyzing the user's transaction history (last 100 transactions by default):

1. **Categorization Patterns**: Study how the user categorizes transactions.
   - Look for recurring merchants/descriptions and their assigned categories
   - Note any uncategorized transactions that might need attention
   - Identify spending trends (e.g., dining out increasing month-over-month)

2. **Spending Insights**:
   - Top 5 spending categories by total amount
   - Average monthly spending per category
   - Unusually large transactions that deviate from the norm
   - Subscription/recurring payments that could be optimized

3. **Income Analysis**:
   - Primary income sources and their stability
   - Irregular income patterns
   - Savings rate trends

4. **Recommendations**:
   - Suggest categories for uncategorized transactions based on similar past transactions
   - Propose new categories if spending patterns suggest them
   - Flag potential budget overruns
"""

FILE_PROCESSING_SKILL = """
## File Processing Skill

When the user uploads a file (PDF statement, CSV, spreadsheet):

1. **PDF Statements**:
   - Extract transaction data (date, description, amount)
   - Match transactions to existing accounts
   - Suggest categories based on the user's transaction history
   - Present a preview before importing

2. **CSV Files**:
   - Parse column headers and suggest mappings
   - Validate data formats (dates, amounts)
   - Preview parsed transactions before bulk import

3. **Spreadsheets**:
   - Read tabular data from Excel files
   - Handle multiple sheets if present
   - Map columns to transaction fields

Always preview before importing — let the user confirm the data looks correct.
"""

USER_SUPPORT_SKILL = """
## User Support Skill

When the user asks for help or seems confused:

1. **Explain Simply**: Break down financial concepts into plain language.
   - Instead of "Your savings rate decreased by 5%", say "You're saving less
     this month compared to last month — here's why..."

2. **Actionable Advice**: Base recommendations on their actual data.
   - "You spend $200/month on coffee shops — brewing at home could save $150/month"
   - "Your grocery spending is 30% above your 3-month average"

3. **Educational**: Help the user understand their financial habits.
   - Explain what different financial metrics mean
   - Show how their decisions affect their overall financial health

4. **Proactive**: Notice patterns and offer suggestions before being asked.
   - "I see a new subscription — want me to track it?"
   - "Your dining budget is almost exhausted for this month"
"""

CATEGORY_INTELLIGENCE_SKILL = """
## Category Intelligence Skill

To provide smart category suggestions:

1. **Learn from History**:
   - When creating a transaction, look at similar past transactions
   - Use the same category for similar merchants/descriptions
   - If the user corrected a category, remember that preference

2. **Smart Suggestions**:
   - "Netflix" → Subscriptions
   - "Grocery Store X" → Groceries
   - "Gas Station Y" → Transportation
   - "Employer Name" → Salary/Income

3. **New Categories**:
   - If a transaction doesn't fit existing categories, propose a new one
   - Explain why the new category makes sense
   - Ask for confirmation before creating

4. **Consistency**:
   - Keep category names consistent (don't create "Coffee" and "Cafes" separately)
   - Suggest merging similar categories if duplicates exist
"""

# Combined skills prompt for injection into the system message
SKILLS_PROMPT = f"""
{TRANSACTION_ANALYSIS_SKILL}

{FILE_PROCESSING_SKILL}

{USER_SUPPORT_SKILL}

{CATEGORY_INTELLIGENCE_SKILL}
"""
