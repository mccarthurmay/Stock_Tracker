from selenium import webdriver
from selenium.webdriver.common.by import By

def scraper(index):
    ticker_list = []

    #activate driver
    driver = webdriver.Chrome()

    #navigate to link of requested index
    is_link = 'https://www.slickcharts.com/' + index
    driver.get(is_link)

    #find all <a> tags with href containing '/symbol/'
    elements = driver.find_elements(By.XPATH, "//a[contains(@href,'/symbol/')]")

    #extract the text after "/symbol/" and append to ticker_list
    for element in elements:
        href_value = element.get_attribute("href")
        ticker_symbol = href_value.split('/symbol/')[-1]
        ticker_list.append(ticker_symbol)

    driver.quit()
    return ticker_list





def main():
    print("Examples: dowjones, sp500, nasdaq100")
    index = input("What index would you like to scrape? ")
    print(scraper(index))
main()
