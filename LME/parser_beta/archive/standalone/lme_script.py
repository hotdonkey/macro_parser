# %%
import pandas as pd
import requests
import numpy as np
from datetime import date
import time
from tqdm import tqdm

# This block is using for upload to google sheets
import gspread
from df2gspread import df2gspread as d2g
from oauth2client.service_account import ServiceAccountCredentials

import signal
from contextlib import contextmanager


# %%
class TimeoutException(Exception): pass

@contextmanager
def time_limit(seconds):
    def signal_handler(signum, frame):
        raise TimeoutException("Timed out!")
    signal.signal(signal.SIGALRM, signal_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)

# %%
# Function for uploading dataframes into the google docs
def google_upload(df, sheet_name):
    # Params used to connect to google api
    scope = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive']
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        '/Users/kirillkuznecov/Documents/data_science_learning/code/LME/parser_beta/standalone/macro-parser-lme-c2f2972b48fc.json', scope) #security token
    gc = gspread.authorize(credentials)

    #Key params for connection to particular document
    spreadsheet_key = '1WhLiXRcdlkG7NCvHac9unC8ROt4lcbY7GxrOEdezZ9s' #document id
    wks_name = sheet_name  # sheet name that we use
    d2g.upload(df, spreadsheet_key, wks_name, credentials=credentials)
    print(f'Uploading to {sheet_name} completed')


def lme_db_addition():

    def get_day_info():

        # URL API for every metall, place into the var
        url_aluminium = 'https://www.lme.com/api/trading-data/day-delayed?datasourceId=1a0ef0b6-3ee6-4e44-a415-7a313d5bd771'
        url_copper = 'https://www.lme.com/api/trading-data/day-delayed?datasourceId=762a3883-b0e1-4c18-b34b-fe97a1f2d3a5'
        url_lead = 'https://www.lme.com/api/trading-data/day-delayed?datasourceId=bc443de6-0bdd-4464-8845-9504f528b0c6'
        url_nikel = 'https://www.lme.com/api/trading-data/day-delayed?datasourceId=acadf037-c13f-42f2-b42a-cac9a8179940'
        url_zink = 'https://www.lme.com/api/trading-data/day-delayed?datasourceId=c389e2b0-c4a3-46a0-96ca-69cacbe90ee4'

        # List for iterations
        req_list = {'aluminium': url_aluminium, 'copper': url_copper,
                    'lead': url_lead, 'nikel': url_nikel, 'zink': url_zink}

        # Empty dict for final row-stage
        day_dict = {'date': [], 'aluminium': [], 'copper': [],
                    'lead': [], 'nikel': [], 'zink': [], }

        # Getting json from api's requests and taking the info (in our case OFFER price for a date)
        for metal, url in req_list.items():
            req = requests.get(url).json()
            metal_dict = req['Rows'][0]
            day_dict[metal] = float(metal_dict['Values'][1])
            day_dict['date'] = metal_dict['BusinessDateTime']

        # Transform dict from previous stage into the row
        dict_ = dict(day_dict)  # Maybe can simplify this
        day_row = pd.DataFrame([dict_])
        day_row.date = pd.to_datetime(day_row.date)

        return day_row  # This is our row for implimentation into the main base

    # Opening main base, add a row, check for dupp, saving and closing
    lme_db = pd.read_excel(
        '/Users/kirillkuznecov/Documents/data_science_learning/code/LME/parser_beta/standalone/LME_db.xlsx', index_col=0)
    day_row = get_day_info()
    lme_db = pd.concat([lme_db, day_row], axis=0, ignore_index=True)
    lme_db.drop_duplicates(inplace=True)

    with pd.ExcelWriter(
        "/Users/kirillkuznecov/Documents/data_science_learning/code/LME/parser_beta/standalone/LME_db.xlsx",
        date_format="YYYY-MM-DD",
            datetime_format="YYYY-MM-DD") as writer:
        lme_db.to_excel(writer, sheet_name='LME_non_ferrous')
    print('LME parsing is DONE!')

    google_upload(lme_db, 'LME_non_ferrous')

    return lme_db


def kitco_db():
    # In KITCO parsing we're taking slightly different aproach, we need to reupload
    # the table into the file because sometimes KITCO changing data backdating
    
    #!!!Need to work out the implementation of previous year data!!!!
    #year = int(date.today().year) - 2001
    
    url = 'https://www.kitco.com/gold.londonfix.html'
    #url_previous_year = f'https://www.kitco.com/londonfix/gold.londonfix{year}.html'
    response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
    #responce_prev = requests.get(url_previous_year, headers={'User-Agent': 'Mozilla/5.0'})

    kitco_response = pd.read_html(response.text)
    kitco_df = pd.read_excel(
        '/Users/kirillkuznecov/Documents/data_science_learning/code/LME/parser_beta/standalone/kitko_db.xlsx', index_col=0)

    # Get the raw table and drop unnesesary rows
    kitco_day = kitco_response[1]
    kitco_day.drop([1, 4, 6], axis=1, inplace=True)
    kitco_day.columns = kitco_day.iloc[0]
    kitco_day.drop([0, 1, 2], axis=0, inplace=True)

    # Change tyoe of data within table
    kitco_day['Date'] = pd.to_datetime(kitco_day['Date'])
    kitco_day = kitco_day.replace({'-': np.nan})
    kitco_day = kitco_day.sort_values(by=['Date'])
    kitco_day = kitco_day.reset_index(drop=True)
    kitco_day[['Gold', 'Silver', 'Platinum', 'Palladium']] = kitco_day[[
        'Gold', 'Silver', 'Platinum', 'Palladium']].apply(pd.to_numeric)

    kitco_day.drop_duplicates(inplace=True)

    # And rewrite old table
    kitco_day.to_excel(
        '/Users/kirillkuznecov/Documents/data_science_learning/code/LME/parser_beta/standalone/kitko_db.xlsx', sheet_name='kitco_metall')
    print('KITCO parsing is DONE!')

    google_upload(kitco_day, 'KITCO')

    return kitco_day


def cb_curr():
    day = date.today()
    today = day.strftime('%d/%m/%Y')

    dict_of_currencies = {
        'R01235': 'USD',
        'R01239': 'EUR',
        'R01010': 'Australian_Dollar',
        'R01375': 'China_Yuan',
        'R01035': 'British_Pound',
        'R01335': 'Kazakhstan_Tenge',
        'R01820': 'Japanese_Yen',
        'R01775': 'Swiss_Franc'
    }

    list_of_currencies = [x for x in dict_of_currencies.keys()]

    URL_list = []
    for currency in list_of_currencies:
        URL = f'http://www.cbr.ru/scripts/XML_dynamic.asp?date_req1={today}&date_req2={today}&VAL_NM_RQ={currency}'
        URL_list.append(URL)

    currency_df = pd.read_excel(
        '/Users/kirillkuznecov/Documents/data_science_learning/code/LME/parser_beta/standalone/cb_curr.xlsx', index_col=0)

    # This problem occurs in the beginning of the year so I was forced to catch a ValueError
    
    try:
        for url_element in URL_list:
            response_df = pd.read_xml(url_element)
            response_df['Date'] = pd.to_datetime(
                response_df['Date'], dayfirst=True)
            response_df['Value'] = response_df['Value'].apply(
                lambda x: x.replace(',', '.'))
            response_df['Value'] = response_df['Value'].apply(pd.to_numeric)
            response_df = response_df.replace(dict_of_currencies)
            currency_df = pd.concat(
                [currency_df, response_df], axis=0, ignore_index=True)
            currency_df.drop_duplicates(inplace=True)
        print('CentroBank_currency parsing is DONE!')

    except ValueError:
        print('Empty data set in CentroBank_currency. Should check the source.')

    with pd.ExcelWriter(
            "/Users/kirillkuznecov/Documents/data_science_learning/code/LME/parser_beta/standalone/cb_curr.xlsx") as writer:
        currency_df.to_excel(writer, sheet_name='curr')

    google_upload(currency_df, 'cb_curr')

    return currency_df


def cb_metall():
    day = date.today()
    today = day.strftime('%d/%m/%Y')

    metall_dict = {
        1: 'gold',
        2: 'silver',
        3: 'platinum',
        4: 'palladium'
    }

    URL = f'http://www.cbr.ru/scripts/xml_metall.asp?date_req1={today}&date_req2={today}'

    metall_df = pd.read_excel(
        '/Users/kirillkuznecov/Documents/data_science_learning/code/LME/parser_beta/standalone/cb_metall.xlsx', index_col=0)

    # This problem occurs in the beginning of the year so I was forced to catch a ValueError
    try:
        response_df = pd.read_xml(URL)
        response_df.drop(columns='Buy', axis=1, inplace=True)
        response_df['Date'] = pd.to_datetime(
            response_df['Date'], dayfirst=True)
        response_df['Sell'] = response_df['Sell'].apply(
            lambda x: x.replace(',', '.'))  # changing for future retyping to numeric
        response_df['Sell'] = response_df['Sell'].apply(pd.to_numeric)
        response_df = response_df.replace(metall_dict)

        metall_df = pd.concat(
            [metall_df, response_df],
            axis=0,
            ignore_index=True)

        metall_df.drop_duplicates(inplace=True)
        print('CentroBank_metalls parsing is DONE!')

    except ValueError:
        print('Empty data set in CentroBank_metalls . Should check the source.')

    with pd.ExcelWriter(
            '/Users/kirillkuznecov/Documents/data_science_learning/code/LME/parser_beta/standalone/cb_metall.xlsx',
            date_format='YYYY-MM-DD',
            datetime_format='YYYY-MM-DD') as writer:
        metall_df.to_excel(writer, sheet_name='cb_metall')

    google_upload(metall_df, 'cb_metall')

    return metall_df

def nbk_tenge():
    #Realy unrelieable source, mb it would be better off with using ms query inside the file
    year = date.today().year

    upper_bound = f'01.01.{year}'
    lower_bound = f'31.12.{year}'

    url = f'https://nationalbank.kz/ru/exchangerates/ezhednevnye-oficialnye-rynochnye-kursy-valyut\
        /report?rates%5B%5D=5&beginDate={upper_bound}&endDate={lower_bound}'
    
    counter = 0
    
    while counter <= 6:
        try:
            with time_limit(15):
                page = requests.get(url=url)
                break
        except TimeoutException as e:
            print("NBK_tenge timed out! Another attempt")
            counter += 1
        
    temp_df = pd.read_html(page.text)
    df =temp_df[0]
    df['Unnamed: 0'] = pd.to_datetime(df['Unnamed: 0'], dayfirst=True)
    
    with pd.ExcelWriter(
            '/Users/kirillkuznecov/Documents/data_science_learning/code/LME/parser_beta/standalone/nbk_tenge.xlsx') as writer:
        df.to_excel(writer, sheet_name='tenge')
    
    print('NBK_tenge parsing is DONE!')
    
    google_upload(df, 'nbk_tenge')
    
    return df


# %%
if __name__ == '__main__':
    lme_db_addition()
    kitco_db()
    cb_curr()
    cb_metall()
    nbk_tenge()

# %%



