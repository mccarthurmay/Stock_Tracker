import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
from api import *
import yfinance as yf

import sqlite3
from datetime import datetime, timedelta
import os

def analyze_8k_sentiment(api_key, item_content):
    """
    Analyze Item 1.01 content using Claude API for stock price movement prediction
    """
    url = "https://api.anthropic.com/v1/messages"
    
    headers = {
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
        "x-api-key": api_key
    }
    
    prompt = f"""Based on this 8-K Item 1.01 content, analyze the likelihood of the stock price increasing or decreasing. 
    Respond ONLY with one of these options followed by percentage chance and confidence:
    "extremely negative [chance]% [confidence]%"
    "negative [chance]% [confidence]%"
    "neutral [chance]% [confidence]%"
    "positive [chance]% [confidence]%"
    "extremely positive [chance]% [confidence]%"
    Do not respond with anything else besides one of the above prompts.
    
    Content to analyze:
    {item_content}
    """
    
    data = {
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "model": "claude-3-opus-20240229",
        "max_tokens": 100
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        sentiment = result['content'][0]['text'].strip()
        return sentiment
    except Exception as e:
        print(f"Error calling Claude API: {e}")
        return None

def get_8k_content(filing_url, headers):
    """
    Get the content of a specific 8-K filing using the text version
    """
    try:
        index_response = requests.get(f"https://www.sec.gov{filing_url}", headers=headers)
        index_soup = BeautifulSoup(index_response.text, 'html.parser')
        
        txt_links = [link['href'] for link in index_soup.find_all('a') if link['href'].endswith('.txt')]
        
        if txt_links:
            doc_response = requests.get(f"https://www.sec.gov{txt_links[0]}", headers=headers)
            content = BeautifulSoup(doc_response.text, 'html.parser').get_text()
            
            # Strip extra whitespace and normalize spaces
            content = ' '.join(content.split())
            
            # Find Item 1.01 section
            start_idx = content.find('Item 1.01')
            if start_idx == -1:
                start_idx = content.find('ITEM 1.01')
                
            if start_idx != -1:
                next_items = ['Item 2', 'Item 3', 'Item 4', 'Item 5', 'Item 6', 'Item 7', 'Item 8', 'Item 9',
                            'ITEM 2', 'ITEM 3', 'ITEM 4', 'ITEM 5', 'ITEM 6', 'ITEM 7', 'ITEM 8', 'ITEM 9']
                end_idx = len(content)
                
                for item in next_items:
                    idx = content.find(item, start_idx + 8)
                    if idx != -1:
                        end_idx = min(end_idx, idx)
                
                extracted_text = content[start_idx:end_idx].strip()
                extracted_text = extracted_text.replace('\n', ' ').replace('\r', ' ')
                extracted_text = ' '.join(extracted_text.split())
                
                return extracted_text
            
        return None
        
    except Exception as e:
        print(f"Error fetching 8-K content: {e}")
        return None

def get_latest_8k_filings(api_key, limit=3):
    """
    Scrape the most recent 8-K filings from SEC website, their content, and sentiment analysis
    """
    url = "https://www.sec.gov/cgi-bin/browse-edgar?company=&CIK=&type=8-k&owner=include&count=40&action=getcurrent"
    headers = {
        'User-Agent': 'Maximillian May mccarthurmay@gmail.com',
        'Accept-Encoding': 'gzip, deflate',
        'Host': 'www.sec.gov'
    }
    
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        filings = []
        rows = soup.find_all('tr')
        
        for i in range(len(rows)):
            row = rows[i]
            company_td = row.find('td', {'bgcolor': '#E6E6E6'})
            
            if company_td:
                company_link = company_td.find('a')
                if company_link:
                    company_text = company_link.text
                    company_name = company_text[:company_text.find('(')].strip()
                    cik = company_text[company_text.find('(')+1:company_text.find(')')].strip()
                    
                    filing_row = rows[i + 1]
                    if filing_row:
                        cols = filing_row.find_all('td')
                        if len(cols) >= 4:
                            filing_desc = cols[2].get_text(strip=True)
                           
                            if 'items 1.01' in filing_desc.lower():
                                items = filing_desc[filing_desc.find('items')+5:filing_desc.find('Accession')].strip()
                                accession = filing_desc[filing_desc.find('Accession Number:')+17:filing_desc.find('Act')].strip()
                                filing_date = cols[3].get_text(strip=True)
                                
                                filing_link = cols[1].find_all('a')[0]['href']
                                
                                item_content = get_8k_content(filing_link, headers)
                                
                                # Get sentiment analysis if content was found
                                sentiment = None
                                if item_content:
                                    sentiment = analyze_8k_sentiment(api_key, item_content)
                                
                                filings.append({
                                    'company': company_name,
                                    'cik': cik,
                                    'items': items,
                                    'filing_date': filing_date,
                                    'accession_number': accession,
                                    'item_101_content': item_content,
                                    'sentiment_analysis': sentiment
                                })
                                
                                if len(filings) >= limit:
                                    break
        
        return pd.DataFrame(filings)
        
    except Exception as e:
        print(f"Error fetching filings: {e}")
        return pd.DataFrame()

def check_penny_stock(cik: str) -> str:
    # Ensure CIK is 10 digits with leading zeros
    cik = str(cik).zfill(10)
    
    # SEC EDGAR submissions endpoint
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    
    headers = {
        'User-Agent': 'Maximillian May mccarthurmay@gmail.com' 
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        # Get trading symbol from response
        symbol = data.get('tickers')
        clean_ticker = symbol[0] 
        print(clean_ticker)
        ticker = yf.Ticker(clean_ticker).history(period = "1d",interval = "1d")
        ticker_price = ticker['Close'].iloc[-1]
        if ticker_price < 5:
            return True
        else:
            return False
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        return True



def initialize_database():
    """
    Create SQLite database and tables if they don't exist
    """
    conn = sqlite3.connect('filing_analysis.db')
    c = conn.cursor()
    
    # Create table for analyzed filings
    c.execute('''
        CREATE TABLE IF NOT EXISTS analyzed_filings
        (cik TEXT,
         filing_date TEXT,
         accession_number TEXT PRIMARY KEY,
         sentiment TEXT,
         analysis_date TEXT)
    ''')
    
    conn.commit()
    conn.close()

def clean_old_entries():
    """
    Remove entries older than 2 days
    """
    conn = sqlite3.connect('filing_analysis.db')
    c = conn.cursor()
    
    two_days_ago = (datetime.now() - timedelta(days=4)).strftime('%Y-%m-%d')
    
    c.execute('DELETE FROM analyzed_filings WHERE analysis_date < ?', (two_days_ago,))
    
    conn.commit()
    conn.close()

def is_filing_analyzed(cik, filing_date, accession_number):
    """
    Check if a filing has already been analyzed
    """
    conn = sqlite3.connect('filing_analysis.db')
    c = conn.cursor()
    
    c.execute('''
        SELECT sentiment FROM analyzed_filings 
        WHERE cik = ? AND filing_date = ? AND accession_number = ?
    ''', (cik, filing_date, accession_number))
    
    result = c.fetchone()
    conn.close()
    
    return result[0] if result else None

def store_analysis(cik, filing_date, accession_number, sentiment):
    """
    Store the analysis results in the database
    """
    conn = sqlite3.connect('filing_analysis.db')
    c = conn.cursor()
    
    analysis_date = datetime.now().strftime('%Y-%m-%d')
    
    c.execute('''
        INSERT OR REPLACE INTO analyzed_filings 
        (cik, filing_date, accession_number, sentiment, analysis_date)
        VALUES (?, ?, ?, ?, ?)
    ''', (cik, filing_date, accession_number, sentiment, analysis_date))
    
    conn.commit()
    conn.close()

def get_latest_8k_filings(api_key, limit=3):
    """
    Modified version of get_latest_8k_filings that skips penny stocks
    """
    # Initialize database if it doesn't exist
    initialize_database()
    
    # Clean old entries
    clean_old_entries()
    
    url = "https://www.sec.gov/cgi-bin/browse-edgar?company=&CIK=&type=8-k&owner=include&count=40&action=getcurrent"
    headers = {
        'User-Agent': 'Maximillian May mccarthurmay@gmail.com',
        'Accept-Encoding': 'gzip, deflate',
        'Host': 'www.sec.gov'
    }
    
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        filings = []
        rows = soup.find_all('tr')
        
        i = 0
        while i < len(rows) and len(filings) < limit:
            row = rows[i]
            company_td = row.find('td', {'bgcolor': '#E6E6E6'})
            
            if company_td:
                company_link = company_td.find('a')
                if company_link:
                    company_text = company_link.text
                    company_name = company_text[:company_text.find('(')].strip()
                    cik = company_text[company_text.find('(')+1:company_text.find(')')].strip()
                    
                    # Check if it's a penny stock
                    if check_penny_stock(cik):
                        print(f"Skipping penny stock: {company_name} (CIK: {cik})")
                        i += 1
                        continue
                    
                    filing_row = rows[i + 1]
                    if filing_row:
                        cols = filing_row.find_all('td')
                        if len(cols) >= 4:
                            filing_desc = cols[2].get_text(strip=True)
                            
                            if 'items 1.01' in filing_desc.lower():
                                items = filing_desc[filing_desc.find('items')+5:filing_desc.find('Accession')].strip()
                                accession = filing_desc[filing_desc.find('Accession Number:')+17:filing_desc.find('Act')].strip()
                                filing_date = cols[3].get_text(strip=True)
                                
                                # Check if we've already analyzed this filing
                                existing_sentiment = is_filing_analyzed(cik, filing_date, accession)
                                
                                if existing_sentiment:
                                    sentiment = existing_sentiment
                                    item_content = None  # Don't need to fetch content for existing analysis
                                else:
                                    filing_link = cols[1].find_all('a')[0]['href']
                                    item_content = get_8k_content(filing_link, headers)
                                    
                                    # Only get new sentiment analysis if content was found
                                    sentiment = None
                                    if item_content:
                                        sentiment = analyze_8k_sentiment(api_key, item_content)
                                        if sentiment:
                                            store_analysis(cik, filing_date, accession, sentiment)
                                
                                filings.append({
                                    'company': company_name,
                                    'cik': cik,
                                    'items': items,
                                    'filing_date': filing_date,
                                    'accession_number': accession,
                                    'item_101_content': item_content,
                                    'sentiment_analysis': sentiment,
                                    'analysis_status': 'Existing' if existing_sentiment else 'New'
                                })
            
            i += 1
            
            # If we've reached the end but haven't found enough non-penny stock filings,
            # we might need to fetch more results
            if i >= len(rows) and len(filings) < limit:
                print("Reached end of current results, might need to fetch more...")
        
        return pd.DataFrame(filings)
        
    except Exception as e:
        print(f"Error fetching filings: {e}")
        return pd.DataFrame()


"""
if __name__ == "__main__":
    api_key =os.getenv("CLAUDE_API_SECRET_KEY"),
    recent_filings = get_latest_8k_filings(api_key, limit=2)
    
    if not recent_filings.empty:
        for idx, filing in recent_filings.iterrows():
            print(f"\nFiling Date: {filing['filing_date']}")
            print(f"Company: {filing['company']}")
            print(f"CIK: {filing['cik']}")
            print(f"Items: {filing['items']}")
            print(f"Analysis Status: {filing['analysis_status']}")
            if filing['item_101_content']:
                print("Item 1.01 Content:")
                print(filing['item_101_content'])
            print("\nSentiment Analysis:")
            print(filing['sentiment_analysis'])
            print("\n" + "="*80)
    else:
        print("No filings found")

        """

if __name__ == "__main__":
    print(check_penny_stock("0001962011"))

