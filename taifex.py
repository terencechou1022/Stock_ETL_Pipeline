import time
import holidays
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select

holiday = holidays.Taiwan()
web = webdriver.Edge()
url = 'https://www.taifex.com.tw/cht/3/futDailyMarketReport'
web.get(url)

for i in pd.date_range('2024-09-01', '2024-09-30'):
    date_str = i.strftime("%Y/%m/%d")

    if date_str in holiday or i.weekday() >= 5:
        continue

    input = web.find_element(By.ID,'queryDate')
    input.clear()
    input.send_keys(date_str)

    select_1 = Select(web.find_element(By.ID, 'MarketCode'))
    select_1.select_by_index(0)

    select_2 = Select(web.find_element(By.ID, 'commodity_idt'))
    select_2.select_by_index(19)

    button = web.find_element(By.ID, 'button')
    button.click()

    time.sleep(5)

    table = pd.read_html(web.page_source)

    date_text = web.find_element(By.XPATH, '//*[@id="printhere"]/p[1]').text.split('：')[1]

    main_table = table[0]
    main_table['日期'] = date_text
    print(main_table)