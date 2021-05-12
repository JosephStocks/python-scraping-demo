import argparse
import json
import os
import pathlib
import re
from operator import itemgetter

import requests
from bs4 import BeautifulSoup

parser = argparse.ArgumentParser(description='Download all form pdfs matching search query within year range (inclusive)')

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

def extractIRSFormInfo(search_query, min_year, max_year, logging=False):
    search_query = search_query.lower()
    result_dict_list = []
    index_of_first_row = 0
    RESULTS_PER_PAGE = 200

    with requests.session() as session:
        # Initial get request to grab the session id
        initial_response = session.get('https://apps.irs.gov/app/picklist/list/priorFormPublication.html')
        soup = BeautifulSoup(initial_response.text, 'html.parser')
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
            data_response = session.get(f"https://apps.irs.gov/app/picklist/list/priorFormPublication.html;jsessionid={jsessionid}", params=params)
            if logging:
                print('#########################################################################')
                print(f"Search Query: {search_query}, Index of First Row: {index_of_first_row}, Results Per Page: {RESULTS_PER_PAGE}")
                print(data_response.url)
            soup2 = BeautifulSoup(data_response.text, 'html.parser')

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
                    year = int(year.text.strip())
                    if form.lower() == search_query and year >= min_year and year <= max_year:
                        link = link['href']
                        description = description.text.strip()
                        if logging:
                            print(f"Form: {form}, Link: {link}, Description: {description}, Year: {year}")
                        result_dict_list.append({'form': form, 'link': link, 'description': description, 'year': year})
            
            # stop when last file number equals the total number of files
            if last_file_num == total_files:
                scraping = False
            else:
                index_of_first_row += RESULTS_PER_PAGE

    return result_dict_list


def downloadFormPDFsWithYearRange(search_query, min_year, max_year, logging=False):
    result_dict_list = extractIRSFormInfo(search_query=search_query, min_year=min_year, max_year=max_year, logging=logging)

    if not result_dict_list:
        print('There are no exact results for that search query. Is it spelled correctly?')
    else:
        try:
            os.mkdir(search_query)
        except FileExistsError as e:
            raise Exception(f"The folder '{search_query}' already exists.") from e

        for form in result_dict_list:
            response = requests.get(form['link'])
            file_name = f"{form['form']} - {form['year']}.pdf"
            with open(pathlib.Path(search_query) / file_name, 'wb') as f:
                f.write(response.content)


downloadFormPDFsWithYearRange(search_query=args.search_query, min_year=args.min_year, max_year=args.max_year, logging=args.logging)

