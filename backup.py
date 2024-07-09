import argparse
import aiohttp
import asyncio
import os
import urllib.parse
import signal
import uvloop
from aiohttp import ClientSession

# Constants
CURSOR_FILE = "cursor.txt"
BATCH_SIZE = 1000
NUM_BATCHES = 10
NUM_WORKERS = 8
MAX_RETRIES = 5
INITIAL_BACKOFF = 1  # Initial backoff time in seconds

# Rate limiting constants based on Cloudflare's official statement
# Reference: https://developers.cloudflare.com/fundamentals/api/reference/limits/
MAX_REQUESTS = 1000  # Stay well within the limit of 1200 requests per 5 minutes
TIME_WINDOW = 300  # 5 minutes in seconds
DELAY = TIME_WINDOW / MAX_REQUESTS  # Delay between requests to stay within the rate limit

# Semaphore to limit the number of concurrent requests
semaphore = asyncio.Semaphore(MAX_REQUESTS)

# Global variable to store the current cursor
current_cursor = None

# Use uvloop for faster event loops
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

# Global variable for debug mode
DEBUG_MODE = False

def log(message, level="info"):
    """
    Custom logging function to handle debug mode.
    """
    if DEBUG_MODE or level == "info":
        print(message)

async def fetch_value(session, name, args):
    """
    Fetch the value for a given key and save it to the destination directory.
    """
    dest = os.path.join(args.dest, name)
    if os.path.exists(dest):
        log(f"{name} already exists; skipping.", "debug")
        return

    log(f"Downloading {name}", "debug")
    headers = {'Authorization': f'Bearer {args.api_token}'}
    url = f'https://api.cloudflare.com/client/v4/accounts/{args.cf_account_id}/storage/kv/namespaces/{args.kv_namespace_id}/values/{urllib.parse.quote(name).replace("/", "%2F")}'
    
    retries = 0
    backoff = INITIAL_BACKOFF

    while retries < MAX_RETRIES:
        async with semaphore:
            async with session.get(url, headers=headers) as r:
                if r.status == 200:
                    content = await r.read()
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with open(dest, "wb+") as f:
                        f.write(content)
                    log(f"Successfully downloaded {name}")
                    return
                elif r.status == 429:
                    log(f"Rate limited. Retrying {name} in {backoff} seconds...", "debug")
                    await asyncio.sleep(backoff)
                    retries += 1
                    backoff *= 2  # Exponential backoff
                else:
                    log(f"Failed to download {name}. Status code: {r.status}, Response: {await r.text()}", "debug")
                    return

    log(f"Exceeded maximum retries for {name}. Skipping.", "debug")

async def fetch_keys(session, args, queue):
    """
    Fetch keys in batches and add them to the queue.
    """
    global current_cursor
    cursor = load_cursor()
    current_cursor = cursor  # Initialize the global cursor
    log(f"Starting with cursor: {cursor}", "debug")

    for _ in range(NUM_BATCHES):
        headers = {'Authorization': f'Bearer {args.api_token}'}
        url = f'https://api.cloudflare.com/client/v4/accounts/{args.cf_account_id}/storage/kv/namespaces/{args.kv_namespace_id}/keys?limit={BATCH_SIZE}&cursor={cursor}'
        
        async with session.get(url, headers=headers) as r:
            if r.status != 200:
                log(f"Failed to fetch keys. Status code: {r.status}, Response: {await r.text()}", "debug")
                break

            data = await r.json()
            log(f"Fetched {len(data['result'])} keys")

            for item in data['result']:
                await queue.put(item['name'])

            if data["result_info"]["cursor"]:
                cursor = data["result_info"]["cursor"]
                current_cursor = cursor  # Update the global cursor
                log(f"New cursor to save: {cursor}", "debug")
                save_cursor(cursor)
                log(f"Saved cursor: {cursor}", "debug")
            else:
                break

async def worker(queue, args):
    """
    Continuously download keys from the queue.
    """
    async with ClientSession() as session:
        while True:
            name = await queue.get()
            if name is None:
                break
            await fetch_value(session, name, args)
            await asyncio.sleep(DELAY)  # Enforce rate limiting delay

def save_cursor(cursor):
    """
    Save the cursor to a file.
    """
    log(f"Saving cursor to file: {cursor}", "debug")
    try:
        with open(CURSOR_FILE, 'w') as f:
            f.write(cursor)
        log("Cursor saved successfully.", "debug")
    except Exception as e:
        log(f"Failed to save cursor: {e}", "debug")

def load_cursor():
    """
    Load the cursor from a file.
    """
    if os.path.exists(CURSOR_FILE):
        with open(CURSOR_FILE, 'r') as f:
            cursor = f.read().strip()
            log(f"Loaded cursor from file: {cursor}", "debug")
            return cursor
    log("No cursor file found, starting from the beginning.", "debug")
    return ""

def signal_handler(signal, frame):
    """
    Handle termination signals to save the cursor state.
    """
    global current_cursor
    log("CTRL+C detected! Saving cursor and shutting down gracefully...", "info")
    if current_cursor:
        save_cursor(current_cursor)
    log("Cursor saved. Exiting now.", "info")
    os._exit(0)

async def main(args):
    """
    Main function to orchestrate the fetching and downloading process.
    """
    global DEBUG_MODE
    DEBUG_MODE = args.debug

    if not args.api_token:
        raise Exception("Missing API token")
    if not args.cf_account_id:
        raise Exception("Missing Cloudflare account ID")
    if not args.kv_namespace_id:
        raise Exception("Missing KV namespace ID")

    os.makedirs(args.dest, exist_ok=True)

    queue = asyncio.Queue()

    async with ClientSession() as session:
        # Create a dedicated task to fetch keys and fill the queue
        producer = asyncio.create_task(fetch_keys(session, args, queue))
        # Create worker tasks to download values
        consumers = [asyncio.create_task(worker(queue, args)) for _ in range(NUM_WORKERS)]
        
        await producer
        for _ in range(NUM_WORKERS):
            await queue.put(None)
        await asyncio.gather(*consumers)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Backup Cloudflare KV store')

    parser.add_argument('--api_token', type=str, help='Cloudflare\'s API token')
    parser.add_argument('--cf_account_id', type=str, help='Cloudflare\'s account tag')
    parser.add_argument('--kv_namespace_id', type=str, help='KV namespace ID')
    parser.add_argument('--dest', type=str, help='Destination backup directory', default="./data")
    parser.add_argument('--num_workers', type=int, help='Number of worker processes', default=NUM_WORKERS)
    parser.add_argument('--debug', action='store_true', help='Enable debug mode for detailed logging')

    args = parser.parse_args()

    # Register the signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    # Run the main function
    asyncio.run(main(args))