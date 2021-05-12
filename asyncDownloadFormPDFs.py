import argparse
import asyncio
import functools
import os
import pathlib
import re

import aiofiles
import aiohttp
from bs4 import BeautifulSoup


# Parses command line arguments (search query, min year, max year, logging)
def parse_cli_args():
    parser = argparse.ArgumentParser(description='Asynchronously download all form pdfs matching search query within year range (inclusive)')

    parser.add_argument('search_query',
                        metavar='search_query',
                        type=str,
                        help='form name search query')
    parser.add_argument('min_year',
                        metavar='min_year',
                        type=int,
                        help='low year in range')
    parser.add_argument('max_year',
                        metavar='max_year',
                        type=int,
                        help='high year in range')

    parser.add_argument('--logging', default=True, action='store_true', help="turn on logging to terminal. Logging is on by default.")
    parser.add_argument('--no-logging', dest='logging', action='store_false', help="turn off logging to terminal")
    args = parser.parse_args()
    return args.search_query, args.min_year, args.max_year, args.logging


# decorator to provide logging functionality for the http get requests
def get_logger(get_func=None, logging=False):
    if get_func is None:
        return functools.partial(get_logger, logging=logging)

    @functools.wraps(get_func)
    async def wrapper_get_logger(session, url, params={}):
        if logging:
            if params:
                print(f"Requesting data | Query: {params['value']}, Row Index: {params['indexOfFirstRow']}")
            else:
                print(f"Requesting {url}")
            value = await get_func(session, url, params)
            if params:
                print(f"Received data | Query: {params['value']}, Row Index: {params['indexOfFirstRow']}")
            else:
                print(f"Received data for {url}")
        else:
            value = await get_func(session, url, params)
        return value
    return wrapper_get_logger

# performs http get request and returns text
async def get(session, url, params={}):
    resp = await session.get(url, params=params)
    data = await resp.text()
    return data

# parses html using BeautifulSoup library
async def bsoup(text):
    return BeautifulSoup(text, 'html.parser')

# performs initial get http request and grabs the jsessionid for subsequent http requests
async def scrape_sessionid(session):
    initial_page_url = "https://apps.irs.gov/app/picklist/list/priorFormPublication.html"
    soup = await bsoup(await get(session, initial_page_url))
    return soup.head.script['src'].split('=')[-1]

# performs the get http request and beautifulsoup html parsing for search result calls
async def data_pull(session, jsessionid, search_query, results_per_page, first_row_index):
    params = {
        'indexOfFirstRow': first_row_index, 
        'sortColumn': 'sortOrder',
        'value': search_query,
        'criteria': 'formNumber',
        'resultsPerPage': results_per_page,
        'isDescending': 'false'
    }
    url = f"https://apps.irs.gov/app/picklist/list/priorFormPublication.html;jsessionid={jsessionid}"
    return await bsoup(await get(session, url, params))

# returns initial search results parsed html AND total files in the search (used to know how many fetch calls to make)
async def pull_first_page_with_total_files(session, jsessionid, search_query, results_per_page):
    data_soup = await data_pull(session, jsessionid, search_query, results_per_page, first_row_index=0)
    total_files_text = data_soup.select('th.ShowByColumn')[0].text.strip().replace('\n','')
    first_file_num, last_file_num, total_files = re.findall(r"\d+(?:[,]\d+)*", total_files_text)
    return data_soup, int(total_files.replace(',', ''))

# takes beautifulsoup parsed html and extracts the form data if it matches search query exactly
async def extract_data_from_html(soup, search_query, min_year, max_year):
    result_dict_list = []
    for row in soup.select('table.picklist-dataTable tr'):
        cells = row.select('td')
        if len(cells) == 3:
            form, description, year = list(cells)
            link = form.select('a')[0]
            form = link.text.strip()
            year = int(year.text.strip().replace(',', ''))
            if form.lower() == search_query.lower() and year >= min_year and year <= max_year:
                link = link['href']
                description = description.text.strip()
                result_dict_list.append({
                    'form': form,
                    'link': link,
                    'description': description,
                    'year': int(year)
                })
    return result_dict_list

# fetches the url for the search results, parses the html for the form row data
async def pull_and_parse_data(session, jsessionid, search_query, results_per_page, first_row_index, min_year, max_year):
    data_soup = await data_pull(session, jsessionid, search_query, results_per_page, first_row_index)
    return await extract_data_from_html(data_soup, search_query, min_year, max_year)

# pulls the pdf url data in the form of bytes, not text
async def get_pdf(session, url):
    resp = await session.get(url)
    return await resp.read()

# writes single pdf file to disk
async def fetch_and_write_pdf(session, form, search_query):
    response_content = await get_pdf(session, form['link'])
    file_name = f"{form['form']} - {form['year']}.pdf"
    async with aiofiles.open(pathlib.Path(search_query) / file_name, 'wb') as f:
        await f.write(response_content)

async def main():
    RESULTS_PER_PAGE = 200 # the number of files/data rows that can result from one http get search request

    # Perform most http get requests within context manager to share session data
    async with aiohttp.ClientSession() as session:
        # initial http get request which scrapes the jsessionid for all later requests
        jsessionid = await scrape_sessionid(session)

        # returns first parsed html search results AND total number of files returned by the search (not all are shown - only 200 are shown)
        # Further requests are needed to grab all results
        first_data_soup, total_files = await pull_first_page_with_total_files(session, jsessionid, search_query, RESULTS_PER_PAGE)

        # Extracts list of dictionary objects for each matching form result (only for initial search page)
        first_data_dict_list = await extract_data_from_html(first_data_soup, search_query, min_year, max_year)

        # Initializes all subsequent http get requests one after another without waiting for the their results (asynchronous). 
        # the gather waits for all of the results to come back.
        results = await asyncio.gather(*[pull_and_parse_data(session, jsessionid, search_query, RESULTS_PER_PAGE, first_row_index, min_year, max_year) 
                                        for first_row_index in range(RESULTS_PER_PAGE, total_files, RESULTS_PER_PAGE)])
        
        # Concatenate all of the lists of dictionaries into one list of dict objects
        combined_dict_list = first_data_dict_list
        for result in results:
            combined_dict_list += result

        if not combined_dict_list:
            print('There are no exact results for that search query. Is it spelled correctly?')
        else:
            # Create folder if it doesn't exist, otherwise give error
            try:
                os.mkdir(search_query)
            except FileExistsError as e:
                raise Exception(f"The folder '{search_query}' already exists.") from e
            
            # fetch each pdf link and write the file to the subdirectory
            for form in combined_dict_list:
                await fetch_and_write_pdf(session, form, search_query)

if __name__ == '__main__':
    search_query, min_year, max_year, logging = parse_cli_args()

    # Manually decorating get function in order to control logging through the command line
    get = get_logger(logging=logging)(get)


    asyncio.run(main())
