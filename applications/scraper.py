from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

chrome_options = Options()
chrome_options.add_argument("--headless")

def check_duplicates(ticker_symbol, filename):
    existing_symbols = []  # Initialize the variable to an empty list
    try:
        with open('new.txt', 'r') as file:
            existing_symbols = [line.strip() for line in file]
    except FileNotFoundError:
        pass
    return ticker_symbol not in existing_symbols


def scraper(index, choice, filename):
    ticker_list = []

    filename = f'{filename}.txt'
    #activate driver
    driver = webdriver.Chrome()#(options=chrome_options)

    #navigate to link of requested index
    is_link = 'https://www.slickcharts.com/' + index
    driver.get(is_link)

    #find all <a> tags with href containing '/symbol/'
    elements = driver.find_elements(By.XPATH, "//a[contains(@href,'/symbol/')]")

    #extract the text after "/symbol/" and append to ticker_list
    for element in elements:
        href_value = element.get_attribute("href")
        ticker_symbol = href_value.split('/symbol/')[-1]

        if ticker_symbol not in ticker_list:
            if choice == 'add':
                if check_duplicates(ticker_symbol, filename):
                    ticker_list.append(ticker_symbol)
            elif choice == 'overwrite':
                ticker_list.append(ticker_symbol)
    if choice == 'add':
        with open(filename,'a') as file:
            for ticker_symbol in ticker_list:
                file.write(f'{ticker_symbol}\n')

    if choice == 'overwrite':
        with open(filename,'w') as file:
            for ticker_symbol in ticker_list:
                file.write(f'{ticker_symbol}\n')

    file.close()
    driver.quit()





def main():
    index = ''
    while index != 'quit':
        print("Examples: dowjones, sp500, nasdaq100")
        index = input("What index would you like to scrape? ")
        filename = input("file wanted:")
        choice = input("add or overwrite to file: ")
        scraper(index, choice, filename)
main()
