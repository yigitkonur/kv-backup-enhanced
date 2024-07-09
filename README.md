# Workers KV Backup

Copy the content of a Workers KV namespace locally with enhanced performance and reliability for backup or data processing needs.

## Credits

This project is an enhanced version of the original script created by [xtuc](https://github.com/xtuc/kv-backup/). The original script can be found [here](https://github.com/xtuc/kv-backup/).

## Enhancements

This enhanced version includes several improvements over the original script:

1. **Asynchronous Programming**: Utilizes `aiohttp` and `asyncio` for non-blocking operations, significantly improving performance.
2. **Rate Limiting**: Implements rate limiting using a semaphore and calculated delay to comply with Cloudflare's rate limits.
3. **Retry Mechanism**: Adds exponential backoff for retrying failed requests, improving reliability.
4. **Cursor Management**: Saves and loads the cursor to handle large datasets and resume from where it left off in case of interruptions.
5. **Graceful Shutdown**: Adds a signal handler to save the cursor on termination, ensuring data integrity.
6. **Worker and Producer Pattern**: Separates fetching keys and downloading values into distinct functions for better modularity.
7. **Configuration Constants**: Defines constants for configurable parameters like batch size, number of workers, and retry settings.
8. **Using `uvloop`**: Sets `uvloop` as the event loop policy for better performance.
9. **Improved Argument Parsing**: Enhances argument parsing for better configurability via command-line arguments.
10. **Debug Mode**: Adds a debug mode for detailed logging to help with troubleshooting and understanding the script's behavior.

## Usage

### Prerequisites

- Python 3.6+
- `aiohttp` and `uvloop` libraries

You can install the required libraries using pip:

```sh
pip install aiohttp uvloop
```

### Running the Script

```sh
python3 ./backup.py --api_token=... --cf_account_id=... --kv_namespace_id=...
```

### Flags

- `api_token`: Cloudflare's API token (Permission: Workers KV readonly)
- `cf_account_id`: Cloudflare's Account ID
- `kv_namespace_id`: Workers KV's namespace ID
- `dest`: Optional, backup location (default is `./data`)
- `num_workers`: Optional, number of worker processes (default is 8)
- `debug`: Optional, enable debug mode for detailed logging

### Example

```sh
python3 ./backup.py --api_token=your_api_token --cf_account_id=your_account_id --kv_namespace_id=your_namespace_id --dest=./backup --num_workers=10 --debug
```

### Debug Mode

The debug mode provides detailed logging to help with troubleshooting and understanding the script's behavior. When enabled, it logs additional information such as:

- When a key already exists and is being skipped.
- When a key is being downloaded.
- Detailed retry information, including backoff times.
- Detailed information about cursor loading and saving.
- Any errors encountered during the process.

To enable debug mode, simply add the `--debug` flag when running the script.

## How It Works

1. **Fetch Keys**: The script fetches keys in batches from the Workers KV namespace using the provided API token, account ID, and namespace ID.
2. **Download Values**: It downloads the values for each key and saves them to the specified destination directory.
3. **Rate Limiting**: Ensures requests stay within Cloudflare's rate limits using a semaphore and calculated delay.
4. **Retry Mechanism**: Retries failed requests with exponential backoff in case of rate limiting or other transient errors.
5. **Cursor Management**: Saves the cursor to a file after each batch to allow resuming from where it left off.
6. **Graceful Shutdown**: Handles termination signals to save the current cursor state before shutting down.
7. **Debug Mode**: Provides detailed logging to help with troubleshooting and understanding the script's behavior.