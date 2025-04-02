import argparse
from datetime import datetime
import os, sys
from time import time
import traceback

# Note: For optimization, custom modules are imported as required
from Utils.commons import colprint_init, colprint, PRINT_THEMES, ExitException
from Utils.commons import create_logger, load_yaml, pretty_time, strip_ansi, threaded, delete_old_logs

ACTIVE_CLIENTS = ['Anime', 'Movies & Shows']
get_current_time = lambda fmt='%F %T': datetime.now().strftime(fmt)

def get_client():
    '''Return a client instance'''
    # add hls_size_accuracy parameter passed from cli
    config.setdefault(series_type, {}).update({'hls_size_accuracy': hls_size_accuracy})
    # Load required Client based on user selection, to avoid unnecessary imports
    if series_type == 'Anime':
        logger.debug('Creating Anime Client for AnimePahe site')
        from Clients.AnimePaheClient import AnimePaheClient
        return AnimePaheClient(config['Anime'])
    elif series_type == 'Movies & Shows':
        logger.debug('Creating KissKh Client for Movies & Shows')
        from Clients.KissKhClient import KissKhClient
        return KissKhClient(config['Movies & Shows'], series_type='Movies & Shows')
    else:
        logger.error(f'Unknown series type: {series_type}')
        raise ExitException(1)

def get_os_safe_path(tmp_path):
    '''Returns OS corrected path with expanded home directory'''
    # First expand the home directory if path starts with ~
    if tmp_path.startswith('~'):
        tmp_path = os.path.expanduser(tmp_path)
        
    if os.sep == '\\' and '/mnt/' in tmp_path:
        # platform is Windows and path is Linux, then convert to Windows path
        logger.debug('Platform is Windows but Paths are Linux. Converting paths to Windows paths')
        tmp_path = tmp_path.split('/')[2:]
        tmp_path[0] = tmp_path[0].upper() + ':'
        tmp_path = '\\'.join(tmp_path)
    elif os.sep == '/' and ':\\' in tmp_path:
        # platform is Linux and path is Windows, then convert to Linux path
        logger.debug('Platform is Linux but Paths are Windows. Converting paths to Linux paths')
        tmp_path = tmp_path.split('\\')
        tmp_path[0] = tmp_path[0].lower().replace(':', '')
        tmp_path = '/mnt/' + '/'.join(tmp_path)
    else:
        tmp_path = tmp_path.replace('/', os.sep).replace('\\', os.sep) # make sure the separator is correct

    return tmp_path

def check_if_exists(path):
    logger.debug(f'Validating/creating download path [{path}]')
    try:
        os.makedirs(path, exist_ok=True)
        logger.debug('Download path exists/created successfully')
    except Exception as e:
        raise Exception(f'Failed to create download path [{path}]. Error: {e}')

def get_series_type(keys, predefined_input=None):
    logger.debug('Selecting the series type')
    types = {}
    menu = '\n\033[96m╭───── SELECT TYPE ─────╮\033[0m\n'
    for idx, typ in enumerate(keys):
        menu += f'\033[94m│ {idx+1}. {typ:<19} │\033[0m\n'
        types[idx+1] = typ
    menu += '\033[96m╰─────────────────────╯\033[0m'
    colprint('header', menu)

    if predefined_input:
        colprint('predefined', f'\nUsing Predefined Input: {predefined_input}')
        series_type = predefined_input
        if series_type not in types:
            logger.error(f'Invalid series type: {series_type}')
            raise ExitException(0)
    else:
        series_type = colprint('user_input', '\nEnter your choice: ', input_type='recurring', input_dtype='int', input_options=types, allow_empty_input=False)

    logger.debug(f'Series type selected: {series_type}')

    return types[series_type]

def search_and_select_series(predefined_search_input=None):
    while True:
        logger.debug("Search and select series")
        # get search keyword from user input
        if predefined_search_input:
            colprint('predefined', f'\nUsing Predefined Input for search: {predefined_search_input}')
            keyword = predefined_search_input
        else:
            keyword = colprint('user_input', "\nEnter series/movie name: ")

        # search with keyword and show results
        colprint('header', "\nSearch Results:")
        logger.info(f'Searching with keyword: {keyword}')
        search_results = client.search(keyword)
        logger.info('Search Results Found')
        logger.debug(f'Search Results: {search_results}')

        if search_results is None or len(search_results) == 0:
            logger.error('No matches found. Try with different keyword')
            if predefined_search_input is None:
                continue
            else:
                raise ExitException(0)

        colprint('header', "\nEnter 0 to search with different key word")

        # get user selection for the search results
        option = colprint('user_input', "\nSelect one of the above: ", input_type='recurring', input_dtype='int', input_options=list(range(len(search_results)+1)), allow_empty_input=False)
        logger.debug(f'Selected option: {option}')

        if option == 0:
            continue
        else:
            break

    return search_results[option]

def get_resolutions(items):
    '''
    Generator function to yield the resolutions of available episodes
    '''
    for item in items:
        yield [ i for i in item.keys() if i not in ('error', 'original') ]

def get_ep_range(default_ep_range, mode='Enter', _episodes_predef=None, type='episodes'):
    '''
    Get the seasons/episodes range from user input.
    Returns dict of start:float, end:float, specific_no:list.
    '''
    if _episodes_predef:
        colprint('predefined', f'\nUsing Predefined Input for {type} to download: {_episodes_predef}')
        ep_user_input = _episodes_predef
    else:
        ep_user_input = colprint('user_input', f"\n{mode} {type} to download (ex: 1-16) [default={default_ep_range}]: ", input_type='recurring', input_dtype='range') or "all"
        if str(ep_user_input).lower() == 'all':
            ep_user_input = default_ep_range

    logger.debug(f'Selected {type} range ({mode = }): {ep_user_input = }')

    # keep track of user input ranges
    if ep_user_input.count('-') > 1:
        logger.error('Invalid input! You must specify only one range.')
        return get_ep_range(default_ep_range, mode, _episodes_predef)

    ep_start, ep_end, specific_eps = 0, 0, []
    for ep_range in ep_user_input.split(','):
        if '-' in ep_range:                             # process the range if '-' is found
            ep_range = ep_range.split('-')
            if ep_range[0] == '':
                ep_range[0] = default_ep_range.split('-')[0]    # set start to default start number, if not set
            if ep_range[1] == '':
                ep_range[1] = default_ep_range.split('-')[1]    # set end to default end number, if not set

            ep_start, ep_end = map(float, ep_range)
        else:
            specific_eps.append(float(ep_range))        # if it is a number and not range, add it to the list

    return {'start': ep_start, 'end': ep_end, 'specific_no': specific_eps}

def get_ep_range_multiple(season_ep_ranges):
    '''
    Get episode ranges per season
    '''
    selected_seasons = get_ep_range(f"{episodes[0]['season']}-{episodes[-1]['season']}", 'Enter', seasons_predef, type='seasons')
    logger.debug(f'Selected seasons: {selected_seasons}')
    # filter out selected seasons only if available
    selected_seasons = { k:v for k,v in season_ep_ranges.items() if (k >= selected_seasons['start'] and k <= selected_seasons['end']) or k in selected_seasons['specific_no'] }
    logger.debug(f'Selected seasons filtered: {selected_seasons}')
    if episodes_predef:
        dl_entire_season = 'n'
    else:
        dl_entire_season = colprint('user_input', f"\nDownload entire season(s) (y|n)? ", input_type='recurring', input_options=['y', 'n', 'Y', 'N']).lower() or 'y'

    # return entire season range
    if dl_entire_season == 'y':
        return selected_seasons

    # get user input for episode ranges per season
    selected_eps = {}
    for k, v in selected_seasons.items():
        selected_eps_per_season = get_ep_range(f"{v['start']}-{v['end']}", f'Enter Season-{k}', episodes_predef)
        selected_eps[k] = selected_eps_per_season

    return selected_eps

def downloader(ep_details, dl_config):
    '''
    Download function where Download Client initialization and download happens.
    Accepts two dicts: download config, episode details. Returns download status.
    '''
    # load color themes
    error_clr = PRINT_THEMES['error'] if not disable_colors else ''
    success_clr = PRINT_THEMES['results'] if not disable_colors else ''
    skipped_clr = PRINT_THEMES['predefined'] if not disable_colors else ''
    reset_clr = PRINT_THEMES['reset'] if not disable_colors else ''

    start = get_current_time()
    start_epoch = int(time())

    out_file = ep_details['episodeName']

    if 'downloadLink' not in ep_details:
        return f'{error_clr}[{start}] Download skipped for {out_file}, due to error: {ep_details.get("error", "Unknown")}{reset_clr}'

    download_type = ep_details['downloadType']
    # set output directory based on series type
    out_dir = dl_config['download_dir']
    if ep_details.get('type', '') == 'tv':
        out_dir = f"{out_dir}{os.sep}Season-{ep_details['season']}"     # add extra folder for season

    # create download client for the episode based on type
    logger.debug(f'Creating download client with {ep_details = }, {dl_config = }')

    if download_type == 'hls':
        logger.debug(f'Creating HLS download client for {out_file}')
        from Utils.HLSDownloader import HLSDownloader
        dlClient = HLSDownloader(dl_config, ep_details)

    elif download_type == 'mp4':
        logger.debug(f'Creating MP4 download client for {out_file}')
        from Utils.BaseDownloader import BaseDownloader
        dlClient = BaseDownloader(dl_config, ep_details)

    else:
        return f'{error_clr}[{start}] Download skipped for {out_file}, due to unknown download type [{download_type}]{reset_clr}'

    logger.info(f'Download started for {out_file}...')

    if os.path.isfile(os.path.join(f'{out_dir}', f'{out_file}')) and os.path.getsize(os.path.join(f'{out_dir}', f'{out_file}')) > 0:
        # skip file if already exists
        return f'{skipped_clr}[{start}] Download skipped for {out_file}. File already exists!{reset_clr}'
    else:
        try:
            # main function where HLS download happens
            status, msg = dlClient.start_download(ep_details['downloadLink'])
        except Exception as e:
            status, msg = 1, str(e)

        # remove target dirs if no files are downloaded
        dlClient._cleanup_out_dirs()

        end = get_current_time()
        if status != 0:
            return f'{error_clr}[{end}] Download failed for {out_file}, with error: {msg}{reset_clr}'

        end_epoch = int(time())
        download_time = pretty_time(end_epoch-start_epoch, fmt='h m s')
        return f'{success_clr}[{end}] Download completed for {out_file} in {download_time}!{reset_clr}'

def batch_downloader(download_fn, links, dl_config, max_parallel_downloads):

    @threaded(max_parallel=max_parallel_downloads, thread_name_prefix='scraper-', print_status=False)
    def call_downloader(link, dl_config):
        return download_fn(link, dl_config)

    dl_status = call_downloader(links.values(), dl_config)

    # show download status at the end, so that progress bars are not disturbed
    print("\033[K") # Clear to the end of line
    width = os.get_terminal_size().columns
    header_clr = PRINT_THEMES['header'] if not disable_colors else ''
    reset_clr = PRINT_THEMES['reset'] if not disable_colors else ''

    colprint('header', '' * width)
    status_str = f'{header_clr}Download Summary:{reset_clr}'
    for status in dl_status:
        status_str += f'\n{status}'
    print(status_str)
    logger.info(strip_ansi(status_str))
    colprint('header', '' * width)

def close_handlers():
    '''
    Close handlers properly to ensure rotation works without issues
    '''
    try:
        for handler in logger.handlers:
            handler.close()
            logger.removeHandler(handler)
    except Exception as e:
        if 'not defined' in str(e): return   # ignore if logger itself is not defined
        print(f'Error while closing log handlers: {e}')


if __name__ == '__main__':
    try:
        # Initialize required variables
        client = None
        skip_restart = False

        # parse cli arguments
        parser = argparse.ArgumentParser(description='Media scraper and downloader for anime, drama, movies and TV shows.')
        parser.add_argument('-c', '--conf', default='config_scraper.yaml',
                         help='configuration file (default: config_scraper.yaml)')
        parser.add_argument('-l', '--log-file', help='custom file name for logging (default: scraper_{YYYYMMDDHHMMSS}.log)')
        parser.add_argument('-s', '--series-type', type=int, help='type of series')
        parser.add_argument('-n', '--series-name', help='name of the series to search')
        parser.add_argument('-S', '--seasons', action='append', help='seasons number to download (only applicable for TV Shows)')
        parser.add_argument('-e', '--episodes', action='append', help='episodes number to download')
        parser.add_argument('-r', '--resolution', type=str, help='resolution to download the episodes')
        parser.add_argument('-d', '--start-download', action='store_true', help='start download immediately or not')
        parser.add_argument('-dc', '--disable-colors', default=False, action='store_true', help='disable colored output')
        parser.add_argument('-hsa', '--hls-size-accuracy', default=0, type=int, choices=range(0, 101), metavar='[0-100]',
                         help='accuracy to display the file size of hls files. Use 0 to disable. Please enable only if required as it is slow')
        parser.add_argument('-dl', '--disable-looping', default=False, action='store_true', help='disable auto-restart')

        args = parser.parse_args()
        config_file = args.conf
        log_file_name = args.log_file
        if log_file_name is None:
            log_file_name = f"scraper_{get_current_time('%Y%m%d%H%M%S')}.log"
        elif not log_file_name.endswith('.log'):
            log_file_name = f'{log_file_name}.log'
        series_type_predef = args.series_type
        series_name_predef = args.series_name
        seasons_predef = '-'.join(args.seasons) if args.seasons else None
        episodes_predef = '-'.join(args.episodes) if args.episodes else None
        resolution_predef = args.resolution
        # convert bool to y/n
        start_download_predef = 'y' if args.start_download else None
        disable_colors = args.disable_colors
        hls_size_accuracy = args.hls_size_accuracy
        disable_looping = args.disable_looping

        # initialize color printer
        colprint_init(disable_colors)

        # Display banner
        banner = '''\033[95m╔══════════════════════════════════════════════════════════════╗
║                     🎬 MEDIA SCRAPER v1.0 🎬                    ║
║           Download Anime, Movies & TV Shows with ease!          ║
╚══════════════════════════════════════════════════════════════╝\033[0m'''
        print(banner)

        # load config from yaml to dict using yaml
        config = load_yaml(config_file)
        downloader_config = config['DownloaderConfig']
        max_parallel_downloads = downloader_config['max_parallel_downloads']

        # create logger
        config['LoggerConfig']['log_file_name'] = log_file_name
        logger = create_logger(**config['LoggerConfig'])
        logger.info('-------------------------------- NEW SCRAPER SESSION --------------------------------')

        logger.info(f'CLI options: {args}')

        # remove older log files
        delete_old_logs(config['LoggerConfig']['log_dir'], config['LoggerConfig'].get('log_retention_days', 7), config['LoggerConfig'].get('log_backup_count', 3))

        # get series type
        series_type = get_series_type(ACTIVE_CLIENTS, series_type_predef)
        logger.info(f'Selected Series type: {series_type}')

        # create client
        client = get_client()
        logger.info(f'Client: {client}')

        # set client specific download configurations
        if series_type == 'Movies & Shows':  # KissKh client
            downloader_config['use_http_client'] = True

        # set respective download dir if present
        if 'download_dir' in config[series_type]:
            logger.debug(f'Setting download dir to [{config[series_type]["download_dir"]}] from series specific configuration')
            downloader_config['download_dir'] = config[series_type]['download_dir']

        # modify path based on the platform OS
        downloader_config['download_dir'] = get_os_safe_path(downloader_config['download_dir'])
        # check if download path exists
        check_if_exists(downloader_config['download_dir'])

        # search in an infinite loop till you get your series
        target_series = search_and_select_series(series_name_predef)
        logger.info(f'Selected series: {target_series}')

        # fetch episode links
        logger.info(f'Fetching episodes list')
        colprint('header', f'\nAvailable Episodes Details:', end=' ')
        episodes = client.fetch_episodes_list(target_series)
        colprint('results', f'{len(episodes)} episodes found.')

        if len(episodes) == 0:
            logger.error('No episodes found in selected series!')
            raise ExitException(1)

        logger.info(f'Displaying episodes list')
        client.show_episode_results(episodes, seasons_predef, episodes_predef)

        # get user input for episodes range and parse start and end number
        if episodes[0].get('type') == 'tv':
            selected_eps = get_ep_range_multiple(client.get_season_ep_ranges(episodes))
        else:
            selected_eps = get_ep_range(f"{episodes[0]['episode']}-{episodes[-1]['episode']}", 'Enter', episodes_predef)

        # filter required episode links and print
        logger.info(f'Fetching episodes based on {selected_eps = }')
        colprint('header', "\nFetching Episodes & Available Resolutions:")
        target_ep_links = client.fetch_episode_links(episodes, selected_eps)
        logger.debug(f'Fetched episodes: {target_ep_links}')

        if len(target_ep_links) == 0:
            logger.error("No episodes are available for download!")
            raise ExitException(1)

        # set output names & make it windows safe
        logger.debug(f'Set output names based on {target_series}')
        series_title, episode_prefix = client.set_out_names(target_series)
        logger.debug(f'{series_title = }, {episode_prefix = }')

        # set target output dir
        downloader_config['download_dir'] = os.path.join(f"{downloader_config['download_dir']}", f"{series_title}")
        logger.debug(f"Final download dir: {downloader_config['download_dir']}")

        # get available resolutions
        valid_resolutions = []
        valid_resolutions_gen = get_resolutions(target_ep_links.values())
        for _valid_res in valid_resolutions_gen:
            valid_resolutions = _valid_res
            if len(valid_resolutions) > 0:
                break   # get the resolutions from the first non-empty episode
        else:
            # set to default if empty
            valid_resolutions = ['360','480','720','1080']

        logger.debug(f'{valid_resolutions = }')

        # get valid resolution from user
        if resolution_predef:
            colprint('predefined', f'\nUsing Predefined Input for resolution: {resolution_predef}')
            resolution = resolution_predef
        else:
            resolution = str(colprint('user_input', f"\nEnter download resolution ({'|'.join(valid_resolutions)}) [default=720]: ", input_type='recurring', input_dtype='int')) or "720"

        logger.info(f'Selected download resolution: {resolution}')

        # get m3u8 link for the specified resolution
        logger.info('Fetching m3u8 links for selected episodes')
        colprint('header', '\nFetching Episode links:')
        target_dl_links = client.fetch_m3u8_links(target_ep_links, resolution, episode_prefix)
        available_dl_count = len([ k for k, v in target_dl_links.items() if v.get('downloadLink') is not None ])
        logger.debug(f'{target_dl_links = }, {available_dl_count = }')

        if len(target_dl_links) == 0:
            logger.error('No episodes available to download! Exiting.')
            raise ExitException(1)

        msg = f'Episodes available for download [{available_dl_count}/{len(target_dl_links)}].'
        colprint('header', f'\n{msg}', end=' ')
        if available_dl_count == 0:
            logger.error('\nNo episodes available to download! Exiting.')
            raise ExitException(1)
        elif start_download_predef:
            colprint('predefined', f'Using Predefined Input for start download: {start_download_predef}')
            proceed = 'y'
        else:
            proceed = colprint('user_input', f"Proceed to download (y|n)? ", input_type='recurring', input_options=['y', 'n', 'Y', 'N', 'e']).lower() or 'y'

        logger.info(f'{msg} Proceed to download? {proceed}')

        if proceed == 'y':
            pass
        elif proceed == 'e':
            # option for user to edit his choices
            new_selected_eps = get_ep_range(f"{selected_eps['start']}-{selected_eps['end']}", 'Edit')
            new_ep_start, new_ep_end = new_selected_eps['start'], new_selected_eps['end']
            # filter target download links based on new range
            target_dl_links = { k:v for k,v in target_dl_links.items() if (k >= new_ep_start and k <= new_ep_end) or k in new_selected_eps['specific_no'] }
            logger.debug(f'Edited {target_dl_links = }')
            colprint('yellow', f'Proceeding to download as per edited range [{new_ep_start} - {new_ep_end}]...')
        else:
            logger.error("Download halted on user input")
            raise ExitException(1)

        # start downloading...
        msg = f"Downloading episode(s) to {downloader_config['download_dir']}..."
        logger.info(msg); colprint('header', f"\n{msg}")
        # invoke downloader using a threadpool
        logger.info(f'Invoking batch downloader with {max_parallel_downloads = }')
        batch_downloader(downloader, target_dl_links, downloader_config, max_parallel_downloads)

    except SystemExit as se:
        # propagate the exit from argparse after printing help or on parse error
        skip_restart = True

    except KeyboardInterrupt as ki:
        logger.error('User interrupted')

    except ExitException as ee:
        # skip restart only if exit code is 0
        if int(str(ee)) == 0: skip_restart = True

    except Exception as e:
        logger.error(f'Error occurred: {e}. Check log for more details.')
        logger.warning(f'Stacktrace: {traceback.format_exc()}')

    finally:
        # Perform any cleanup tasks
        if client: client.cleanup()
        # Ensure to close handlers at the end of the script or before rotating
        close_handlers()
        # Auto-start a new instance
        if skip_restart or disable_looping: exit(0)
        try:
            continuation_prompt = colprint('user_input', '\nReady for one more? Start new download (y|n)? ', input_type='recurring', input_options=['y', 'n', 'Y', 'N']).lower() or 'y'
            if continuation_prompt == 'y':
                os.system(f'{sys.executable} {sys.argv[0]} -c {config_file} -l {log_file_name}')
            else:
                colprint('results', "Download completed. Thanks for using the scraper!\n")

        except KeyboardInterrupt:
            exit(0)
