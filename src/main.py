import asyncio
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
import yfinance as yfin
from pandas_datareader import data as pdr
import pandas as pd
from datetime import datetime
import gzip
import io
import os
from azure.storage.blob import BlobClient, BlobServiceClient
import uvicorn
from dotenv import load_dotenv

load_dotenv()
app = FastAPI(title="Financial Data Source Service")

# Configuration for Azure Blob Storage
AZURE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
AZURE_CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME", "")

# Initialize Azure Blob Service Client
blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
blob_container_client = blob_service_client.get_container_client(AZURE_CONTAINER_NAME)

# In-memory cache and locks
cache = {}  # asset_id -> Pandas DataFrame
asset_locks = {}  # asset_id -> asyncio.Lock
cache_lock = asyncio.Lock()  # To protect access to asset_locks


class DataResponse(BaseModel):
    asset_id: str
    data: dict


def is_macro_metric(asset_id: str) -> bool:
    """
    Determine if the asset_id corresponds to a macroeconomic metric.
    For simplicity, assume that macro metrics start with 'M_'.
    """
    return asset_id.startswith("M_")


async def fetch_yahoo_finance(asset_id: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Fetch historical data for a stock from Yahoo Finance.
    """
    try:
        ticker = yfin.Ticker(asset_id)
        hist = ticker.history(start=start_date, end=end_date, auto_adjust=False)
        if hist.empty:
            raise ValueError(f"No data found for ticker {asset_id}")
        return hist
    except Exception as e:
        raise ValueError(f"Error fetching data from Yahoo Finance for {asset_id}: {str(e)}")


async def fetch_fred(asset_id: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Fetch macroeconomic data from FRED.
    """
    try:
        df = pdr.get_data_fred(asset_id, start=start_date, end=end_date)
        if df.empty:
            raise ValueError(f"No data found for FRED series {asset_id}")
        return df
    except Exception as e:
        raise ValueError(f"Error fetching data from FRED for {asset_id}: {str(e)}")


async def backup_to_azure(asset_id: str, data: pd.DataFrame):
    """
    Compress and upload the data to Azure Blob Storage asynchronously.
    """
    try:
        # Convert DataFrame to CSV
        csv_buffer = io.StringIO()
        data.to_csv(csv_buffer)
        csv_bytes = csv_buffer.getvalue().encode('utf-8')

        # Compress using gzip
        with io.BytesIO() as gzip_buffer:
            with gzip.GzipFile(mode='wb', fileobj=gzip_buffer) as gz_file:
                gz_file.write(csv_bytes)
            compressed_data = gzip_buffer.getvalue()

        # Define blob name
        blob_name = f"{asset_id}.csv.gz"

        # Create a BlobClient
        blob_client = blob_container_client.get_blob_client(blob_name)

        # Upload the compressed data
        await asyncio.to_thread(blob_client.upload_blob, compressed_data, overwrite=True)
        print(f"Backup successful for {asset_id}")
    except Exception as e:
        print(f"Error backing up data for {asset_id}: {str(e)}")


async def get_or_create_lock(asset_id: str) -> asyncio.Lock:
    """
    Retrieve an existing lock for the asset_id or create a new one.
    """
    async with cache_lock:
        if asset_id not in asset_locks:
            asset_locks[asset_id] = asyncio.Lock()
        return asset_locks[asset_id]


@app.get("/data", response_model=DataResponse)
async def get_data(
    asset_id: str = Query(..., description="Asset ID or macroeconomic metrics ID"),
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format")
):
    """
    Endpoint to retrieve financial or macroeconomic data.
    """
    # Validate date formats
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        if start_dt > end_dt:
            raise HTTPException(status_code=400, detail="start_date must be before end_date")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    lock = await get_or_create_lock(asset_id)

    async with lock:
        # Check if data is in cache
        if asset_id in cache:
            cached_df = cache[asset_id]
            available_start = cached_df.index.min().date()
            available_end = cached_df.index.max().date()
            needs_fetch = False

            if start_dt < available_start or end_dt > available_end:
                needs_fetch = True
        else:
            needs_fetch = True

        if needs_fetch:
            # Determine data source
            if is_macro_metric(asset_id):
                fetched_df = await fetch_fred(asset_id, start_date, end_date)
            else:
                fetched_df = await fetch_yahoo_finance(asset_id, start_date, end_date)

            # Update cache
            if asset_id in cache:
                cache[asset_id] = pd.concat([cache[asset_id], fetched_df]).drop_duplicates().sort_index()
            else:
                cache[asset_id] = fetched_df

            # Start backup in background
            asyncio.create_task(backup_to_azure(asset_id, cache[asset_id]))

        # Retrieve the requested range from cache
        cached_df = cache[asset_id]
        mask = (cached_df.index.date >= start_dt) & (cached_df.index.date <= end_dt)
        result_df = cached_df.loc[mask]
        print(result_df.head())
        if result_df.empty:
            raise HTTPException(status_code=404, detail="No data found for the specified range.")

        # Convert DataFrame to dictionary
        data_dict = result_df.to_dict(orient="split")
        return DataResponse(asset_id=asset_id, data=data_dict)


if __name__ == "__main__":
    # Run the application with uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)