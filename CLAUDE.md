# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Language Policy

**CRITICAL**: When communicating with users in issues, PRs, or comments, you MUST use **Traditional Chinese (繁體中文)**. This applies to:
- Issue comments and responses
- Pull request reviews and comments
- Error explanations and debugging guidance
- Documentation updates (when user-facing)

**English is acceptable for**:
- Code (variables, functions, classes, comments)
- Commit messages (following conventional commit format)
- Branch names
- Internal technical execution and logging
- Code documentation (docstrings, inline comments)

## Project Overview

NASTool is a media library automation tool for NAS environments. It integrates with PT sites, Douban, media servers (Emby/Jellyfin/Plex), download clients (qBittorrent/Transmission), and notification services (WeChat/Telegram/Slack) to automate media collection, organization, and library management.

**Core workflow**: RSS subscription → Download monitoring → Media recognition → File transfer (hardlink/copy/move/rclone) → Media server refresh → Notification

## Development Commands

### Local Development
```bash
# Install dependencies
python3 -m pip install -r requirements.txt
python3 -m pip install -r third_party.txt

# Set config path (required)
export NASTOOL_CONFIG="/path/to/config/config.yaml"

# Run application
python3 run.py

# Access web UI
# Default: http://localhost:3000
# Default credentials: admin/password
```

### Docker Development
```bash
# Build image
docker build -f docker/Dockerfile -t nas-tools:test .

# Run container
docker run -d \
  --name nas-tools-dev \
  -p 3000:3000 \
  -v $(pwd)/config:/config \
  -e NASTOOL_AUTO_UPDATE=false \
  nas-tools:test

# Enter container for debugging
docker exec -it nas-tools-dev sh

# View logs
docker logs -f nas-tools-dev
```

### Manual File Transfer (for testing)
```bash
# Syntax: python3 app/filetransfer.py -m <mode> -s <source> -d <dest>
# Modes: link (hardlink), copy, softlink, move

# Example: hardlink transfer
export NASTOOL_CONFIG=config/config.yaml
python3 app/filetransfer.py -m link -s /from/path -d /to/path
```

## Architecture

### Entry Point
- `run.py`: Main entry, initializes DB, starts scheduler/monitor/brush tasks, launches Flask app
- Environment variables:
  - `NASTOOL_CONFIG`: Config file path (required)
  - `NASTOOL_LOG`: Log directory path
  - `NASTOOL_AUTO_UPDATE`: Auto-update on container restart (Docker only)

### Core Modules (`app/`)

**Media Processing Pipeline**:
- `app/media/meta/`: Media metadata parsing
  - `metainfo.py`: Main parser, extracts title/year/season/episode from filenames
  - `metaanime.py`: Anime-specific parser using anitopy
  - `metavideo.py`: Standard video parser
- `app/media/`: TMDB/Douban/Bangumi integration for metadata lookup
- `app/filetransfer.py`: File transfer engine (hardlink/copy/move/rclone/minio)
- `app/filter.py`: Resource filtering (resolution/quality/size/team)
- `app/media/scraper.py`: NFO/poster scraping for media servers

**Download & Indexing**:
- `app/downloader/`: Download client abstraction (qBittorrent/Transmission/Aria2/115)
- `app/indexer/`: Torrent indexer clients (Jackett/Prowlarr/builtin)
- `app/rss.py`: RSS feed aggregation and subscription management
- `app/rsschecker.py`: Custom RSS task executor
- `app/searcher.py`: Torrent search across indexers

**Site Management**:
- `app/sites/`: PT site automation
  - `sitecookie.py`: Cookie management and auto-login
  - `siteuserinfo/`: Site-specific user stats parsers
- `app/brushtask.py`: Automated seeding/brushing tasks

**Services & Integration**:
- `app/mediaserver/`: Media server clients (Emby/Jellyfin/Plex) for library refresh and webhook
- `app/message/`: Notification clients (WeChat/Telegram/Slack/Bark/etc.)
- `app/scheduler.py`: APScheduler-based task scheduler
- `app/sync.py`: Directory monitoring with watchdog
- `app/doubansync.py`: Douban "Wish to Watch" sync

**Database**:
- `app/db/`: SQLAlchemy models and database layer
  - `main_db.py`: SQLite database for downloads/transfers/config
  - `media_db.py`: Optional media metadata cache
  - `models.py`: ORM models

**Web Interface** (`web/`):
- `web/main.py`: Flask application factory
- `web/action.py`: API endpoints for UI operations
- `web/apiv1.py`: RESTful API v1 (swagger available at `/api/v1/`)

### Third-Party Libraries
Third-party Python packages are listed in `third_party.txt` and loaded from `third_party/` subdirectories at runtime (see `run.py:16-23`). Key packages:
- `feapder`: Web scraping framework for site data extraction
- `qbittorrent-api`, `transmission-rpc`: Download client APIs
- `anitopy`: Anime filename parser
- `plexapi`: Plex server integration

### Configuration
- `config/config.yaml`: Main configuration (TMDB key, paths, transfer modes, etc.)
  - File is monitored; changes trigger hot-reload (see `run.py:154-187`)
- `config/default-category.yaml`: Media category template
- Transfer modes: `link` (hardlink), `copy`, `softlink`, `move`, `rclone`, `minio`

## Critical Implementation Patterns

### File Transfer Modes
When working with file transfer logic (`app/filetransfer.py`):
- **Hardlink (`link`)**: Requires source and destination on same filesystem/partition
- **Docker consideration**: Parent directories must be mapped to same mount point
- **Path mapping**: In Docker, container paths ≠ host paths; use consistent mapping for softlinks
- Always preserve original files when using `link`/`copy`/`rclone` modes
- Use `move` mode with caution (breaks seeding)

### Media Recognition Flow
1. Parse filename → `MetaInfo` object (title, year, season, episode)
2. Query TMDB/Douban → Enrich metadata (ID, poster, plot)
3. Apply category rules → Determine target path
4. Format output filename → Apply rename templates
5. Execute transfer → Use configured RmtMode

### Chinese Optimization
- Media naming optimized for Chinese titles and Emby/Jellyfin/Plex scraping
- Use `zhconv` for Traditional/Simplified Chinese conversion
- Douban integration for Chinese content metadata (fallback to TMDB)
- Anime detection via keywords and anitopy parsing

### Singleton Pattern
Many services use singleton pattern via `app/utils/commons.py:INSTANCES`. When modifying services:
- Implement `init_config()` method for hot-reload support
- Register in `INSTANCES` if config-dependent
- See `run.py:174-177` for reload mechanism

### Database Migrations
- Use Alembic for schema changes (see `app/db/`)
- `init_db()` creates initial schema
- `update_db()` runs migrations on startup
- Always test migrations on copy of production DB first

## Testing Considerations

### Manual Testing Workflow
1. Set up test config: Copy `config/config.yaml.template` (if exists) or use minimal config
2. Required config: `rmt_tmdbkey`, `login_user`, `login_password`
3. Test transfer: Use `app/filetransfer.py` CLI with test files
4. Verify: Check target directory structure matches media server expectations

### Docker Testing
- Use `NASTOOL_AUTO_UPDATE=false` to prevent auto-update during tests
- Map test directories with consistent paths for hardlink testing
- Set `PUID`/`PGID` to match file ownership requirements

### Common Issues
- **Hardlink fails**: Check if source/dest are on same filesystem (`df -h`)
- **Recognition fails**: Verify filename format and TMDB API key
- **Transfer hangs**: Check `_min_filesize` config (default 100MB)
- **Cookie expired**: Site auto-login may fail; update cookies manually

## Configuration Reference

### Essential Config Keys (config.yaml)
- `app.rmt_tmdbkey`: TMDB API key (required for media recognition)
- `app.tmdb_domain`: `api.tmdb.org` or `api.themoviedb.org`
- `media.movie_path`: Movie library path(s) (list)
- `media.tv_path`: TV library path(s) (list)
- `media.rmt_mode`: Default transfer mode (`link`/`copy`/`move`/`rclone`)
- `laboratory.remove_unknown_path`: Unknown media destination

### Format Templates
- `media.movie_dir_rmt_format`: Movie directory naming
- `media.movie_file_rmt_format`: Movie file naming
- `media.tv_dir_rmt_format`: TV show directory naming
- `media.tv_season_rmt_format`: TV season directory naming
- `media.tv_file_rmt_format`: TV episode file naming
- Default formats defined in `config/__init__.py`: `DEFAULT_MOVIE_FORMAT`, `DEFAULT_TV_FORMAT`

## Remote Control

### WeChat/Telegram Commands
- Direct message: Trigger search across indexers
- `/rss`: RSS subscription management
- `/ptt`: Manual file transfer
- `/ptr`: Remove torrents
- `/pts`: Site login
- `/rst`: Directory sync
- `/db`: Douban sync

### Webhook Endpoints
- `/emby`, `/jellyfin`, `/plex`: Media server playback notifications
- `/wechat`: WeChat callback (requires Token/EncodingAESKey)
- `/telegram`: Telegram bot webhook (ports: 443/80/88/8443 with HTTPS)

## GitHub Actions Integration

The repository includes Claude Code Actions for automation:
- `.github/workflows/claude-issue-resolver.yml`: Auto-fix issues with `claude-fix` label
- `.github/workflows/claude-code-review.yml`: PR code review
- `.github/workflows/claude.yml`: Issue/PR comment handling with `@claude` mention
- `.github/workflows/claude-triage.yml`: Auto-label new issues

Allowed tools for issue resolver include Python execution (`python`, `python3`, `pip`, `pytest`) for testing fixes.
