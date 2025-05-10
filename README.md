# financial_data_source
A financial data source which provides data to other applications

## How does it work
the data source accepts HTTP requests and fetch the financial data from the internet.
The requests contains the asset ID or macroeconomic metrics ID, start date, end date. this service first check local cache, if the data range of certain time series doesn't exist the service fetches it from internet, either Yahoo finance (use yfin.Ticker(stock_name).history) or FED (use pdr.get_data_fred).
The service need to backup the entire cached data in Azure on daily basis. and when it starts up, it need to load the cache from Azure Blob storage.
The service is developed based on fastAPI in Python.

The service supports multiple threads, it setup the thread lock on the asset ID level. In such way, the requests for different asset do not interfere each other.
