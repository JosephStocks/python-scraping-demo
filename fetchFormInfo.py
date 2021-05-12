import argparse
import json
import re
from operator import itemgetter
from pprint import pprint

import requests
from bs4 import BeautifulSoup

# Parse command line arguments
parser = argparse.ArgumentParser(description='Download all form pdfs matching search query within year range (inclusive)')

parser.add_argument('search_queries',
                    metavar='search_queries',
                    nargs='+',
                    type=str,
                    help='form name search queries. Can list multiple separated by space. Put single quotes around each query.')
parser.add_argument('-o', '--output', dest='output', type=str, default='output.json', help="specify the file name for the json output file. Defaults to 'output.json'")

parser.add_argument('--logging', default=True, action='store_true', help="turn on logging to terminal. Logging is on by default.")
parser.add_argument('--no-logging', dest='logging', action='store_false', help="turn off logging to terminal")

args = parser.parse_args()

search_queries, output_file_name, logging = args.search_queries, args.output, args.logging

# fetches all data, parses html, returns list of dict objects for each matching data row
def extractIRSFormInfo(search_query, logging=False):
    search_query = search_query.lower()
    result_dict_list = []
    index_of_first_row = 0
    RESULTS_PER_PAGE = 200

    # share session info across http get requests using context manager
    with requests.session() as s:
        # Initial get request to grab the session id
        r = s.get('https://apps.irs.gov/app/picklist/list/priorFormPublication.html')
        soup = BeautifulSoup(r.text, 'html.parser')
        jsessionid = soup.head.script['src'].split('=')[-1]
        scraping = True

        # Pull each page of data until there is no more, save if it matches our query exactly
        while(scraping):
            params = {
                'indexOfFirstRow': index_of_first_row, 
                'sortColumn': 'sortOrder',
                'value': search_query,
                'criteria': 'formNumber',
                'resultsPerPage': RESULTS_PER_PAGE,
                'isDescending': 'false'
            }
            r2 = s.get(f"https://apps.irs.gov/app/picklist/list/priorFormPublication.html;jsessionid={jsessionid}", params=params)
            if logging:
                print('#########################################################################')
                print(f"Search Query: {search_query}, Index of First Row: {index_of_first_row}, Results Per Page: {RESULTS_PER_PAGE}")
                print(r2.url)
            soup2 = BeautifulSoup(r2.text, 'html.parser')

            # Find out the last file index and the total number of files
            total_files_text = soup2.select('th.ShowByColumn')[0].text.strip().replace('\n','')
            first_file_num, last_file_num, total_files = re.findall(r"\d+(?:[,]\d+)*", total_files_text)
            if logging:
                print(f"Last File Number: {last_file_num}, Total Files: {total_files}")
            
            # Loop through each data table row and, if matching, load into array of dicts.
            for row in soup2.select('table.picklist-dataTable tr'):
                cells = row.select('td')
                if len(cells) == 3:
                    form, description, year = list(cells)
                    link = form.select('a')[0]
                    form = link.text.strip()
                    if form.lower() == search_query:
                        link = link['href']
                        description = description.text.strip()
                        year = year.text.strip()
                        if logging:
                            print(f"Form: {form}, Link: {link}, Description: {description}, Year: {year}")
                        result_dict_list.append({'form': form, 'link': link, 'description': description, 'year': int(year)})
            
            # stop when last file number equals the total number of files
            if last_file_num == total_files:
                scraping = False
            else:
                index_of_first_row += RESULTS_PER_PAGE

    return result_dict_list

# converts list of row data dict objects into summary dictionary for single query
def singleFormInfoSummary(search_query, logging=False):
    result_dict_list = extractIRSFormInfo(search_query=search_query, logging=logging)
    result_dict_list = sorted(result_dict_list, key=itemgetter('year'), reverse=False)
    min_year, max_year = result_dict_list[0]['year'], result_dict_list[-1]['year']
    form_title = result_dict_list[0]['description']
    return {'form_number': search_query, 'form_title': form_title, 'min_year': min_year, 'max_year': max_year}

# gathers all summary dictionary objects for all queries into one list of summary dictionaries
def multipleFormInfoSummary(search_queries, logging=False):
    results = []
    for query in search_queries:
        try:
            results.append(singleFormInfoSummary(search_query=query, logging=logging))
        except IndexError:
            print(f"Skipping search query: {query}. There are no exact results for that search query. Is it spelled correctly?")

    return results

# execute function for all search queries
dict_result = multipleFormInfoSummary(search_queries, logging)
if logging:
    print(f"\n{output_file_name}:")
    pprint(dict_result)

# convert list of dictionaries to json and write to file
with open(output_file_name, 'w') as outfile:
    json.dump(dict_result, outfile, indent=2)
