# Remove existing author info
import re
from quickjs import Context as quickjsContext
from urllib.parse import quote_plus

from Clients.BaseClient import BaseClient


class KissKhClient(BaseClient):
    '''
    Client for kisskh site supporting Hollywood movies and TV shows
    '''
    def __init__(self, config, session=None, series_type=None):
        self.series_type = series_type
        self.base_url = config.get('base_url', 'https://kisskh.co/')
        self.search_url = self.base_url + config.get('search_url', 'api/DramaList/Search?q=')
        self.series_url = self.base_url + config.get('series_url', 'api/DramaList/Drama/')
        self.episode_url = self.base_url + config.get('episode_url', 'api/DramaList/Episode/{id}.png?kkey=')
        self.subtitles_url = self.base_url + config.get('subtitles_url', 'api/Sub/{id}?kkey=')
        self.preferred_urls = config['preferred_urls'] if config.get('preferred_urls') else []
        self.blacklist_urls = config['blacklist_urls'] if config.get('blacklist_urls') else []
        self.selector_strategy = config.get('alternate_resolution_selector', 'lowest')
        self.hls_size_accuracy = config.get('hls_size_accuracy', 0)
        super().__init__(config.get('request_timeout', 30), session=session)
        self.logger.debug(f'KissKh client initialized with {config = }')
        self.token_generation_js_code = None
        self.quickjs_context = None
        # site specific details required to create token
        self.subGuid = "VgV52sWhwvBSf8BsM3BRY9weWiiCbtGp"
        self.viGuid = "62f176f3bb1b5b8e70e39932ad34a0c7"
        self.appVer = "2.8.10"
        self.platformVer = 4830201
        self.appName = "kisskh"
        # key and iv for decrypting subtitles
        self.DECRYPT_SUBS_KEY = b'8056483646328763'
        self.DECRYPT_SUBS_IV = b'6852612370185273'
        self.DECRYPT_SUBS_KEY2 = b'AmSmZVcH93UQUezi'
        self.DECRYPT_SUBS_IV2 = b'ReBKWW8cqdjPEnF6'

    def _show_search_results(self, key, details):
        '''Pretty print search results'''
        line = f"{key}: {details.get('title')} | Country: {details.get('country')}" + \
               f"\n   | Episodes: {details.get('episodesCount', 'NA')} | Released: {details.get('year')} | Status: {details.get('status')}"
        self._colprint('results', line)

    def _get_token(self, episode_id, uid):
        '''Create token required to fetch stream & subtitle links'''
        # js code to generate token from kisskh site
        if self.token_generation_js_code is None:
            self.logger.debug('Fetching token generation js code...')
            soup = self._get_bsoup(self.base_url + 'index.html')
            common_js_url = self.base_url + [i['src'] for i in soup.select('script') if i.get('src') and 'common' in i['src']][0]
            self.token_generation_js_code = self._send_request(common_js_url)

        # quickjs context for evaluating js code
        if self.quickjs_context is None:
            self.logger.debug('Creating quickjs context...')
            self.quickjs_context = quickjsContext()

        # evaluate js code to generate token
        self.logger.debug(f'Evaluating js code to generate token using {episode_id = } and {uid = }')
        token = self.quickjs_context.eval(self.token_generation_js_code + f'_0x54b991({episode_id}, null, "2.8.10", "{uid}", 4830201, "kisskh", "kisskh", "kisskh", "kisskh", "kisskh", "kisskh")')
        return token

    def search(self, keyword, search_limit=10):
        '''Search for content based on keyword'''
        search_types = {
            '1': 'Asian Drama',
            '2': 'Asian Movies',
            '3': 'Anime',
            '4': 'Hollywood'
        }
        idx = 1
        search_results = {}

        # Get search type based on client description
        self.logger.debug(f'Filtering content for series_type: {self.series_type}')
        search_type = None
        if self.series_type and 'hollywood' in self.series_type.lower():
            self.logger.debug('Setting search type to Hollywood only')
            search_type = '4'  # Hollywood content only
        else:
            self.logger.debug('No content type filter applied')

        # url encode search keyword
        search_key = quote_plus(keyword)

        for code, type in search_types.items():
            # Skip non-Hollywood content when Hollywood is selected
            if search_type == '4' and code != '4':
                continue
            # Skip Hollywood content when Asian is selected
            if search_type is None and code == '4':
                continue
            # Skip header for filtered content types
            if search_type and search_type != code:
                continue

            # Show Hollywood header only when filtering for Hollywood
            header = "Hollywood" if search_type == '4' else type
            self._colprint('blurred', f"-------------- {header} --------------")
            
            self.logger.debug(f'Searching for {type} with keyword: {keyword}')
            search_url = self.search_url + search_key + '&type=' + str(code)
            search_data = self._send_request(search_url, return_type='json')[:search_limit]

            # Get basic details available from the site
            for result in search_data:
                series_id = result['id']
                self.logger.debug(f'Fetching additional details for series_id: {series_id}')
                series_data = self._send_request(self.series_url + str(series_id), return_type='json')
                item = {
                    'title': series_data['title'],
                    'series_id': series_id,
                    'country': series_data['country'],
                    'episodesCount': series_data['episodesCount'],
                    'series_type': series_data['type'],
                    'status': series_data['status'],
                    'episodes': series_data['episodes']
                }
                try:
                    item['year'] = series_data['releaseDate'].split('-')[0]
                except:
                    item['year'] = 'XXXX'

                # Add index to every search result
                search_results[idx] = item
                self._show_search_results(idx, item)
                idx += 1

        return search_results

    def fetch_episodes_list(self, target):
        '''Fetch episode information'''
        all_episodes_list = []
        episodes = target['episodes']

        self.logger.debug(f'Extracting episode details for {target["title"]}')
        for episode in episodes:
            ep_no = int(episode['number']) if str(episode['number']).endswith('.0') else episode['number']
            ep_name = f"{target['title']} Movie" if target['series_type'].lower() == 'movie' else f"{target['title']} Episode {ep_no}"
            all_episodes_list.append({
                'episode': ep_no,
                'episodeName': self._windows_safe_string(ep_name),
                'episodeId': episode['id'],
                'episodeSubs': episode['sub']
            })

        return all_episodes_list[::-1]   # return episodes in ascending

    def show_episode_results(self, items, *predefined_range):
        '''Display episode list'''
        start, end = self._get_episode_range_to_show(items[0].get('episode'), items[-1].get('episode'), predefined_range[1], threshold=24)
        display_prefix = 'Movie' if items[0].get('episodeName').endswith('Movie') else 'Episode'

        for item in items:
            if item.get('episode') >= start and item.get('episode') <= end:
                fmted_name = re.sub(r'\b(\d$)', r'0\1', item.get('episodeName'))
                self._colprint('results', f"{display_prefix}: {fmted_name}")

    def fetch_episode_links(self, episodes, ep_ranges):
        '''Fetch download links for episodes'''
        download_links = {}
        ep_start, ep_end, specific_eps = ep_ranges['start'], ep_ranges['end'], ep_ranges.get('specific_no', [])
        display_prefix = 'Movie' if episodes[0].get('episodeName').endswith('Movie') else 'Episode'

        for episode in episodes:
            if (float(episode.get('episode')) >= ep_start and float(episode.get('episode')) <= ep_end) or (float(episode.get('episode')) in specific_eps):
                self.logger.debug(f'Processing {episode = }')

                self.logger.debug('Fetching stream token')
                token = self._get_token(episode.get('episodeId'), self.viGuid)
                self.logger.debug(f'Fetching stream link')
                dl_links = self._send_request(self.episode_url.format(id=str(episode.get('episodeId'))) + token, return_type='json')
                if dl_links is None:
                    self.logger.warning(f'Failed to fetch stream link for episode: {episode.get("episode")}')
                    continue

                self.logger.debug(f'Got video response: {dl_links}')
                video_data = dl_links.get('Video', {})
                if isinstance(video_data, str):
                    link = video_data
                    self.logger.debug(f'Direct video link: {link}')
                else:
                    # Try to get different quality options
                    qualities = video_data.get('qualities', {})
                    self.logger.debug(f'Available qualities: {qualities}')
                    # Use highest quality as default
                    link = qualities.get('1080', qualities.get('720', qualities.get('480', video_data.get('url'))))
                    self.logger.debug(f'Selected quality link: {link}')

                # skip if no stream link found
                if link is None:
                    continue

                # check if link has countdown timer for upcoming releases
                if 'tickcounter.com' in link:
                    self.logger.debug(f'Episode {episode.get("episode")} is not released yet')
                    self._show_episode_links(episode.get('episode'), {'error': 'Not Released Yet'}, display_prefix)
                    continue

                # add episode details & stream link to scraper dict
                self._update_scraper_dict(episode.get('episode'), episode)
                self._update_scraper_dict(episode.get('episode'), {'streamLink': link, 'refererLink': self.base_url})

                # get subtitles
                if episode.get('episodeSubs', 0) > 0:
                    self.logger.debug('Subtitles found. Fetching subtitles token')
                    token = self._get_token(episode.get('episodeId'), self.subGuid)
                    self.logger.debug('Fetching subtitles for the episode...')
                    subtitles = self._send_request(self.subtitles_url.format(id=str(episode.get('episodeId'))) + token, return_type='json')
                    subtitles = {sub['label']: sub['src'] for sub in subtitles}
                    self._update_scraper_dict(episode.get('episode'), {'subtitles': subtitles})

                    # Handle subtitle decryption
                    encrypted_subs_details = {}
                    for k, v in subtitles.items():
                        self.logger.debug(f'Checking encryption type for {k} language...')
                        encryption_type = v.split('?')[0].split('.')[-1]
                        if encryption_type == 'txt':
                            encrypted_subs_details[k] = {'key': self.DECRYPT_SUBS_KEY, 'iv': self.DECRYPT_SUBS_IV, 'decrypter': self._aes_decrypt}
                        elif encryption_type == 'txt1':
                            encrypted_subs_details[k] = {'key': self.DECRYPT_SUBS_KEY2, 'iv': self.DECRYPT_SUBS_IV2, 'decrypter': self._aes_decrypt}
                        elif encryption_type == 'srt':
                            continue    # no encryption
                        else:
                            self.logger.warning(f"Unknown encryption type found: {encryption_type}")

                    if encrypted_subs_details:
                        self.logger.debug(f'Encrypted subtitles found. Adding decryption details')
                        self._update_scraper_dict(episode.get('episode'), {'encrypted_subs_details': encrypted_subs_details})

                # Create quality options if we have a video data object
                if isinstance(dl_links.get('Video'), dict):
                    qualities = dl_links['Video'].get('qualities', {})
                    m3u8_links = {}
                    for quality, quality_link in qualities.items():
                        m3u8_links[quality] = {'file': quality_link, 'type': 'mp4' if '.mp4' in quality_link else 'hls'}
                else:
                    # Single quality link
                    link_type = 'mp4' if '.mp4' in link else 'hls'
                    m3u8_links = {'720': {'file': link, 'type': link_type}}

                self.logger.debug(f'Available quality options: {list(m3u8_links.keys())}')

                download_links[episode.get('episode')] = m3u8_links
                self._show_episode_links(episode.get('episode'), m3u8_links, display_prefix)

        return download_links

    def set_out_names(self, target_series):
        '''Set output names for downloads'''
        drama_title = self._windows_safe_string(target_series['title'])
        target_dir = drama_title if drama_title.endswith(')') else f"{drama_title} ({target_series['year']})"
        return target_dir, None
