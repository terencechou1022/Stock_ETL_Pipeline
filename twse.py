import json
import requests
import pandas as pd

def convert_year(date):
    date = date.split('/')
    date[0] = str(int(date[0]) + 1911)
    return '/'.join(date)

for i in pd.date_range('2024-01-01', '2024-12-31', freq = 'M'):
    date_str = i.strftime('%Y%m%d')
    url = f'https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?date={date_str}&stockNo=2330&response=json&_=1727489965804'
    response = requests.get(url)
    data = json.loads(response.text)
    df = pd.DataFrame(data['data'])
    df.columns = data['fields']

    df['成交股數'] = df['成交股數'].str.replace(',', '').astype(float)
    df['成交金額'] = df['成交金額'].str.replace(',', '').astype(float)
    df['成交筆數'] = df['成交筆數'].str.replace(',', '').astype(float)

    df['日期'] = df['日期'].apply(convert_year)
    df['日期'] = pd.to_datetime(df['日期'])
    df = df.set_index('日期')
    print(df)