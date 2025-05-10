# financial_data_source
A financial data source which provides data to other applications

## How does it work
the data source accepts HTTP requests and fetch the financial data from the internet.
The requests contains the asset ID or macroeconomic metrics ID, start date, end date. this service first check local cache, if the data range of certain time series doesn't exist in the in-memory cache nor in the Azure storage, the service fetches it from internet. it could be either Yahoo finance (use yfin.Ticker(stock_name).history) or FED (use pdr.get_data_fred).

The service need to backup the cached data in Azure if it is changed asynchoronously, it should not impact the response time. In Azure Blob we store multiple compressed files, each for an asset or metrics.
The service is developed based on fastAPI in Python.

we use below library for Azure Blob access:
```
from azure.storage.blob import BlobClient, BlobServiceClient
```

Because of the I/O bound nature, we use asyncio to keep the service single threaded.
