# Developer Guide

## Project Structure

```
scraper/
├── Clients/             # Client implementations for different sources
│   ├── AnimePaheClient.py
│   ├── AsianDramaClient.py
│   ├── BaseClient.py    # Base class for all clients
│   ├── GogoAnimeClient.py
│   └── KissKhClient.py
├── Utils/               # Utility modules
│   ├── BaseDownloader.py
│   ├── commons.py       # Common utilities
│   └── HLSDownloader.py # HLS stream handler
├── scraper.py          # Main script
├── config_scraper.yaml # Configuration file
└── requirements.txt    # Python dependencies
```

## Adding New Sources

1. Create a new client class in the Clients directory
2. Inherit from BaseClient
3. Implement required methods:
   - search()
   - fetch_episodes_list()
   - fetch_episode_links()
   - fetch_m3u8_links()
4. Add client to ACTIVE_CLIENTS in scraper.py

## Configuration

The config_scraper.yaml file contains:
- Download directory settings
- Client-specific configurations
- Logger settings
- Downloader settings (threads, timeout, etc.)

## Logging

- Logs are stored in the logs directory
- Default log level is INFO
- Configure retention and rotation in config_scraper.yaml
