import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select

web = webdriver.Edge()
url = 'https://www.tdcc.com.tw/portal/zh/smWeb/qryStock'
web.get(url)

for i in range(5):
    select = Select(web.find_element(By.ID, 'scaDate'))
    select.select_by_index(i)

    input = web.find_element(By.ID, 'StockNo')
    input.clear()
    input.send_keys('2330')
    
    button = web.find_element(By.XPATH, '//*[@id="form1"]/table/tbody/tr[4]/td/input')
    button.click()

    time.sleep(5)

    table = pd.read_html(web.page_source)

    date_text = web.find_element(By.CLASS_NAME, 'font').text.split('：')[1]

    main_table = table[1]
    main_table['日期'] = date_text
    print(main_table)