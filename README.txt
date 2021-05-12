

I wrote two versions for each utility: a synchronous and an asynchronous version.
This results in four total files.

Each utility is fully commented to explain how it works.

Python version: 3.8.7
To install dependencies:
    pip install -r requirements.txt


    Top dependencies: beautifulsoup4 requests aiohttp aiofiles

Part 1 Utility:

    Synchronous version: fetchFormInfo.py
    3rd Party Dependencies:
        requests
        beautifulsoup4
    
    How to call:
    python fetchFormInfo.py 'Form W-2' 'Form 1040' -o outputtest.json --no-logging
    python fetchFormInfo.py 'Form W-2' 'Form 1040' 'Form 1098' -o outputtest2.json --logging
    Also, can be called with '--help' flag to give more details on the arguments

    Asynchronous version: asyncFetchFormInfo.py
    3rd Party Dependencies:
        aiohttp
        beautifulsoup4

    How to call:
    python asyncFetchFormInfo.py 'Form W-2' 'Form 1040' -o outputtest.json --no-logging
    python asyncFetchFormInfo.py 'Form W-2' 'Form 1040' 'Form 1098' -o outputtest2.json --logging
    Also, can be called with '--help' flag to give more details on the arguments



    Speed Comparison
    python fetchFormInfo.py 'Form W-2' 'Form 1040' 'Form 1040-EZ' 'Form W-4' 'Form 1099-MISC' -o outputtest.json --no-logging
    Ran in 2.10s

    python asyncFetchFormInfo.py 'Form W-2' 'Form 1040' 'Form 1040-EZ' 'Form W-4' 'Form 1099-MISC' -o outputtest.json --no-logging
    Ran in 1.28s

    Referencing https://stackoverflow.com/questions/28403939/how-to-calculate-percentage-improvement-in-response-time-for-performance-testing
    for speedup calculations
    The async version reduced time by 39%.
    The async version represents performance increase of 64%.
    The async version is 1.6x faster.

    * These are rough calculations because I didn't average multiple runs.


Part 2 Utility:

    *By Design, part 2 utilities give error if the folder already exits. I'd rather give error then overwrite work.

    synchronous version: downloadFormPDFs.py
    3rd Party Dependencies:
        requests
        beautifulsoup4
    
    How to call:
    python downloadFormPDFs.py 'Form W-2' 2001 2020 --logging
    python downloadFormPDFs.py 'Form W-2' 2010 2015 --no-logging
    Also, can be called with '--help' flag to give more details on the arguments


    asynchronous version: asyncDownloadFormPDFs.py
    3rd Party Dependencies:
        aiohttp
        aiofiles
        beautifulsoup4

    How to call:
    python asyncDownloadFormPDFs.py 'Form W-2' 2001 2020 --logging
    python asyncDdownloadFormPDFs.py 'Form W-2' 2010 2015 --no-logging
    Also, can be called with '--help' flag to give more details on the arguments



    Speed Comparison
    python downloadFormPDFs.py 'Form 1040' 2001 2020 --no-logging
    Ran in 5.19s

    python asyncDownloadFormPDFs.py 'Form 1040' 2001 2020 --no-logging
    Ran in 2.38s

    Referencing https://stackoverflow.com/questions/28403939/how-to-calculate-percentage-improvement-in-response-time-for-performance-testing
    for speedup calculations
    The async version reduced time by 54%.
    The async version represents performance increase of 118%.
    The async version is 2.2x faster.

    * These are rough calculations because I didn't average multiple runs.