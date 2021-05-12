import argparse
import asyncio
import functools
import json
import re
import sys
from operator import itemgetter
from pprint import pprint

import aiohttp
from bs4 import BeautifulSoup


# Parses command line arguments: search query (as many as desired), output file name (default is output.json)
def parse_cli_args():
    parser = argparse.ArgumentParser(description='Download all form pdfs matching search query within year range (inclusive); Asynchronous version')

    parser.add_argument('search_queries',
                        metavar='search_queries',
                        nargs='+',
                        type=str,
                        help='form name search queries. Can list multiple separated by space. Put single quotes around each query.')

    parser.add_argument('-o', '--output', dest='output', type=str, default='output.json', help="specify the file name for the json output file. Defaults to 'output.json'")

    parser.add_argument('--logging', default=True, action='store_true', help="turn on logging to terminal. Logging is on by default.")
    parser.add_argument('--no-logging', dest='logging', action='store_false', help="turn off logging to terminal")

    args = parser.parse_args()
    return args.search_queries, args.output, args.logging


# decorator to provide logging functionality for the http get requests
def get_logger(get_func=None, logging=True):
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
async def extract_data_from_html(soup, search_query):
    result_dict_list = []
    for row in soup.select('table.picklist-dataTable tr'):
        cells = row.select('td')
        if len(cells) == 3:
            form, description, year = list(cells)
            link = form.select('a')[0]
            form = link.text.strip()
            if form.lower() == search_query.lower():
                link = link['href']
                description = description.text.strip()
                year = year.text.strip()
                result_dict_list.append({
                    'form': form,
                    'link': link,
                    'description': description,
                    'year': int(year)
                })
    return result_dict_list

# fetches the url for the search results, parses the html for the form row data
async def pull_and_parse_data(session, jsessionid, search_query, results_per_page, first_row_index):
    data_soup = await data_pull(session, jsessionid, search_query, results_per_page, first_row_index)
    return await extract_data_from_html(data_soup, search_query)

# sorts list of dict objects by year, grabs min year and max year then returns summary dict object
async def summarize_form_info(result_dict_list, search_query):
    result_dict_list = sorted(result_dict_list, key=itemgetter('year'), reverse=False)
    min_year, max_year = result_dict_list[0]['year'], result_dict_list[-1]['year']
    form_title = result_dict_list[0]['description']
    return {'form_number': search_query, 'form_title': form_title, 'min_year': min_year, 'max_year': max_year}

# performs all get requests, parses html, and summarizes for one search query
async def pull_parse_and_summarize_single_query(session, jsessionid, search_query, results_per_page):
    first_data_soup, total_files = await pull_first_page_with_total_files(session, jsessionid, search_query, results_per_page)
    first_data_dict_list = await extract_data_from_html(first_data_soup, search_query)
    results = await asyncio.gather(*[pull_and_parse_data(session, jsessionid, search_query, results_per_page, first_row_index) for first_row_index in range(results_per_page, total_files, results_per_page)])
    combined_dict_list = first_data_dict_list
    for result in results:
        combined_dict_list += result

    if not combined_dict_list:
        print(f"Skipping search query: {search_query}. There are no exact results for that search query. Is it spelled correctly?")
        return
    
    return await summarize_form_info(combined_dict_list, search_query)

async def main():
    RESULTS_PER_PAGE = 200 # the number of files/data rows that can result from one http get search request    

    # Perform most http get requests within context manager to share session data
    async with aiohttp.ClientSession() as session:
        # initial http get request which scrapes the jsessionid for all later requests
        jsessionid = await scrape_sessionid(session)
        
        # starts each search query fetching, parsing, and summarizing one after another without waiting for results
        # asyncio gather collects all the results as each query finishes
        final_result = await asyncio.gather(*[pull_parse_and_summarize_single_query(session, jsessionid, search_query, RESULTS_PER_PAGE) for search_query in search_queries])

        # filter out unmatched queries
        final_result = [summary for summary in final_result if summary is not None]

    if logging:
        print(f"\n{output_file_name}:")
        pprint(final_result)
    
    # write list of dict objects to json file
    with open(output_file_name, 'w') as outfile:
        json.dump(final_result, outfile, indent=2)

if __name__ == '__main__':
    search_queries, output_file_name, logging = parse_cli_args()

    # Manually decorating get function in order to control logging through the command line
    get = get_logger(logging=logging)(get)

    asyncio.run(main())
