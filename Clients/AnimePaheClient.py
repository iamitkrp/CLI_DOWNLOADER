import json
import re
from urllib.parse import quote_plus
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from time import sleep
from Clients.BaseClient import BaseClient

class AnimePaheClient(BaseClient):
    def __init__(self, config, session=None):
        self.base_url = config.get('base_url', 'https://animepahe.ru/')
        self.search_url = self.base_url + config.get('search_url', 'api?m=search&q=')
        self.episodes_list_url = self.base_url + config.get('episodes_list_url', 'api?m=release&sort=episode_asc&id=')
        self.download_link_url = self.base_url + config.get('download_link_url', 'api?m=links&p=kwik&id=')
        self.episode_url = self.base_url + config.get('episode_url', 'play/{anime_id}/{episode_id}')
        self.anime_id = ''
        self.selector_strategy = config.get('alternate_resolution_selector', 'lowest')
        self.hls_size_accuracy = config.get('hls_size_accuracy', 0)
        super().__init__(config['request_timeout'], session)

    def _get_new_cookies(self, url, check_condition, max_retries=3, wait_time_in_secs=5):
        driver = self._get_undetected_chrome_driver(client='AnimePaheClient')
        driver.get(url)

        retry_cnt = 1
        while retry_cnt <= max_retries:
            try:
                driver.find_element(By.XPATH, check_condition)
                break
            except NoSuchElementException:
                retry_cnt += 1
                sleep(wait_time_in_secs)

        if retry_cnt > max_retries:
            driver.quit()
            raise Exception(f'Failed to load site within {max_retries*wait_time_in_secs} seconds')

        all_cookies = driver.get_cookies()
        driver.close()
        driver.quit()

        return {cookie['name']: cookie['value'] for cookie in all_cookies}

    def _get_site_cookies(self, url):
        cookies = self._load_scraper_cookies(client='animepahe')

        if cookies:
            resp = self._send_request(url, cookies=cookies)
            if resp is not None:
                return cookies

        cookies = self._get_new_cookies(url, '/html/body/header/nav/a/img')
        self._save_scraper_cookies(client='animepahe', data=cookies)
        return cookies

    def _show_search_results(self, key, details):
        title = details.get('title')
        box_width = max(len(title), 40)  # minimum width of 40 characters
        info = f"╭{'─' * (box_width + 4)}╮\n"
        info += f"│ {title:<{box_width+2}} │\n"
        info += f"├{'─' * (box_width + 4)}┤\n"
        info += f"│ Type: {details.get('type', ''):<{box_width-4}} │\n"
        info += f"│ Episodes: {details.get('episodes', ''):<{box_width-8}} │\n"
        info += f"│ Released: {details.get('year', '')}, {details.get('season', ''):<{box_width-19}} │\n"
        info += f"│ Status: {details.get('status', ''):<{box_width-6}} │\n"
        info += f"│ Selection: {key:<{box_width-9}} │\n"
        info += f"╰{'─' * (box_width + 4)}╯"
        self._colprint('results', info)

    def _get_kwik_links_v2(self, ep_link):
        response = self._get_bsoup(ep_link, cookies=self.cookies)

        links = response.select('div#resolutionMenu button')
        sizes = response.select('div#pickDownload a')

        resolutions = {}
        for l,s in zip(links, sizes):
            resltn = l['data-resolution']
            current_audio = l['data-audio']
            current_codec = l['data-av1']
            if resltn in resolutions and current_codec != '1':
                continue
            if current_audio == 'eng':
                continue
            resolutions[resltn] = {
                'kwik': l['data-src'],
                'audio': current_audio,
                'codec': current_codec,
                'filesize': s.text.strip()
            }

        return resolutions

    def _show_episode_links(self, key, details):
        info = f"Episode: {self._safe_type_cast(key)}"
        for _res, _vals in details.items():
            filesize = _vals['filesize']
            try:
                filesize = filesize / (1024**2)
                info += f' | {_res}P ({filesize:.2f} MB) [{_vals["audio"]}]'
            except:
                info += f' | {filesize} [{_vals["audio"]}]'

        self._colprint('results', info)

    def get_m3u8_content(self, kwik_link, ep_no):
        referer_link = self.scraper_episode_dict[ep_no]['episodeLink']
        return self._send_request(kwik_link, referer=referer_link)

    def parse_m3u8_link(self, text):
        x = r"\}\('(.*)'\)*,*(\d+)*,*(\d+)*,*'((?:[^'\\]|\\.)*)'\.split\('\|'\)*,*(\d+)*,*(\{\})"
        try:
            p, a, c, k, e, d = re.findall(x, text)[0]
            p, a, c, k, e, d = p, int(a), int(c), k.split('|'), int(e), {}
        except Exception:
            raise Exception('Unable to extract stream link')

        def e(c):
            x = '' if c < a else e(int(c/a))
            c = c % a
            return x + (chr(c + 29) if c > 35 else '0123456789abcdefghijklmnopqrstuvwxyz'[c])

        for i in range(c): 
            d[e(i)] = k[i] or e(i)
        parsed_js_code = re.sub(r'\b(\w+)\b', lambda e: d.get(e.group(0)) or e.group(0), p)

        parsed_link = self._regex_extract('http.*.m3u8', parsed_js_code, 0)
        if not parsed_link:
            raise Exception('Stream link not found')

        return parsed_link

    def search(self, keyword, search_limit=10):
        self.cookies = self._get_site_cookies(self.base_url)
        search_url = self.search_url + quote_plus(keyword)
        response = self._send_request(search_url, cookies=self.cookies, return_type='json')
        response = response['data'] if response['total'] > 0 else None

        if response is not None:
            response = {idx+1:result for idx, result in enumerate(response)}
            for idx, item in response.items():
                self._show_search_results(idx, item)

        return response

    def fetch_episodes_list(self, target):
        session = target.get('session')
        self.anime_id = session
        list_episodes_url = self.episodes_list_url + session

        raw_data = self._send_request(list_episodes_url, cookies=self.cookies, return_type='json')
        episodes_data = raw_data['data']

        last_page = int(raw_data['last_page'])
        if last_page > 1:
            for pgno in range(2, last_page+1):
                episodes_data.extend(self._send_request(f'{list_episodes_url}&page={pgno}', 
                                                     cookies=self.cookies, 
                                                     return_type='json').get('data', []))

        return episodes_data

    def show_episode_results(self, items, *predefined_range):
        start, end = self._get_episode_range_to_show(items[0].get('episode'), 
                                                    items[-1].get('episode'), 
                                                    predefined_range[1], 
                                                    threshold=30)

        for item in items:
            if item.get('episode') >= start and item.get('episode') <= end:
                self._colprint('results', 
                             f"Episode: {self._safe_type_cast(item.get('episode'))} | "
                             f"Audio: {item.get('audio')} | Duration: {item.get('duration')} | "
                             f"Release date: {item.get('created_at')}")

    def fetch_episode_links(self, episodes, ep_ranges):
        download_links = {}
        ep_start = ep_ranges['start']
        ep_end = ep_ranges['end']
        specific_eps = ep_ranges.get('specific_no', [])

        for episode in episodes:
            ep_num = float(episode.get('episode'))
            if (ep_num >= ep_start and ep_num <= ep_end) or (ep_num in specific_eps):
                episode_link = self.episode_url.format(anime_id=self.anime_id, 
                                                     episode_id=episode.get('session'))
                links = self._get_kwik_links_v2(episode_link)

                if not links:
                    continue

                self._update_scraper_dict(episode.get('episode'),
                                    {'episodeId': episode.get('session'), 
                                     'episodeLink': episode_link})
                download_links[episode.get('episode')] = links
                self._show_episode_links(episode.get('episode'), links)

        return download_links

    def set_out_names(self, target_series):
        anime_title = self._windows_safe_string(target_series['title'])
        target_dir = f"{anime_title} ({target_series['year']})"
        anime_type = 'Movie' if target_series.get('type').lower() == 'movie' else 'Episode'
        episode_prefix = f"{anime_title} {anime_type}"
        return target_dir, episode_prefix

    def fetch_m3u8_links(self, target_links, resolution, episode_prefix):
        def _get_ep_name(resltn):
            return f"{episode_prefix}{' ' if episode_prefix.lower().endswith('movie') and len(target_links.items()) <= 1 else f' {ep} '}- {resltn}P.mp4"

        for ep, link in target_links.items():
            error = None
            info = f'Episode: {self._safe_type_cast(ep)} |'

            selected_resolution = self._resolution_selector(link.keys(), resolution, self.selector_strategy)
            res_dict = link.get(selected_resolution)

            if 'error' in link:
                error = link.get('error')
            elif not res_dict:
                error = f'Resolution [{resolution}] not found'
            else:
                info = f'{info} {selected_resolution}P |'
                try:
                    ep_name = self._windows_safe_string(_get_ep_name(selected_resolution))
                    kwik_link = res_dict['kwik']
                    raw_content = self.get_m3u8_content(kwik_link, ep)
                    ep_link = self.parse_m3u8_link(raw_content)

                    self._update_scraper_dict(ep, {'episodeName': ep_name,
                                             'refererLink': kwik_link,
                                             'downloadLink': ep_link, 
                                             'downloadType': 'hls'})
                    self._colprint('results', f'{info} Link found [{ep_link}]')

                except Exception as e:
                    error = f'Failed to fetch link with error [{e}]'

            if error:
                ep_name = _get_ep_name(resolution)
                self._update_scraper_dict(ep, {'episodeName': ep_name, 'error': error})

        return {k:v for k,v in self._get_scraper_dict().items()}
