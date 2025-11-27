import re
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

def clean_text(text):
    """Cleans text for PDF compatibility (latin-1 encoding)."""
    if text is None: return ""
    text = str(text)
    replacements = {
        "\u2013": "-", "\u2014": "-", "\u2018": "'", "\u2019": "'", 
        "\u201c": '"', "\u201d": '"', "\u2022": "*", 
        "✅": "", "⚠️": "", "🔄": "", "🆕": ""
    }
    for char, repl in replacements.items():
        text = text.replace(char, repl)
    return text.encode('latin-1', 'replace').decode('latin-1')

def calculate_financial_periods(take_on_date_str, year_end_str):
    """Calculates financial periods based on Take-On Date and Year End."""
    try:
        take_on_date = datetime.strptime(str(take_on_date_str), "%Y-%m-%d")
        first_of_take_on = take_on_date.replace(day=1)
        request_end_date = first_of_take_on - timedelta(days=1) 
        
        months = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6, 
                  'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
        ye_month = 2 
        for m_name, m_val in months.items():
            if m_name in str(year_end_str).lower():
                ye_month = m_val
                break
        
        start_month = ye_month + 1
        if start_month > 12: start_month = 1
        
        candidate_year = request_end_date.year
        if start_month > request_end_date.month:
             candidate_year -= 1
        
        current_fin_year_start = datetime(candidate_year, start_month, 1)
        if current_fin_year_start > request_end_date:
            current_fin_year_start -= relativedelta(years=1)
            
        current_period_str = f"Financial records from {current_fin_year_start.strftime('%d %B %Y')} to {request_end_date.strftime('%d %B %Y')}"
        
        historic_end_date = current_fin_year_start - timedelta(days=1)
        historic_start_date = current_fin_year_start - relativedelta(years=5)
        historic_period_str = f"{historic_start_date.strftime('%d %B %Y')} to {historic_end_date.strftime('%d %B %Y')}"
            
        bank_start = take_on_date - relativedelta(months=1)
        bank_str = f"Bank account statements as of {bank_start.strftime('%d %B %Y')} as well as confirmation that the funds has been paid over to Pretor Group."
        
        owner_bal_str = f"Owner balances to be provided on {request_end_date.strftime('%d %B %Y')}."
        closing_date = take_on_date + timedelta(days=10)
        closing_bal_str = f"Final bank closing balances to be provided by {closing_date.strftime('%d %B %Y')} as well as confirmation that the funds has been paid over to Pretor Group."

        return current_period_str, historic_period_str, bank_str, owner_bal_str, closing_bal_str
    except Exception:
        return "Current Financial Year Records", "Past 5 Financial Years", "Latest Bank Statements", "Owner Balances", "Final Closing Balances"
