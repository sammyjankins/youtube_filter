# -*- coding: utf-8 -*-
# python 3.8
# instead of requirements: pip install --upgrade google-api-python-client
import csv
import json
import re
from datetime import date

from googleapiclient.discovery import build

from settings import api_key


class YouTubeFilter:
    youtube = build('youtube', 'v3', developerKey=api_key)
    re_date = re.compile(r'[^T]+')

    def __init__(self,
                 link: str,
                 min_views: int = 0,
                 max_views: int = 999999999999,
                 min_date: str = None,
                 max_date: str = None,
                 ascending: bool = False,
                 sort_by_date: bool = False):
        """
        Filtering a YouTube playlist based on the parameters.

        :param link: link to channel or playlist
        :param min_views: at least
        :param max_views: no more than
        :param min_date: uploaded not earlier (example of format '2018-01-01')
        :param max_date: uploaded no later than (example of format '2019-01-01')
        :param ascending: if True - list in ascending order
        :param sort_by_date: if True - sort by upload date
        """

        self.link = link
        self.yt_username = None
        self.playlist = None
        self.channel_request = None
        self.next_page = None
        self.min_views = min_views
        self.max_views = max_views
        self.min_date = min_date
        self.max_date = max_date
        self.videos = dict()
        self.portions = list()
        self.sorted_keys = list()
        self.ascending = ascending
        self.sort_by_date = sort_by_date
        self.link_type_init()

    def __str__(self):
        return self.yt_username

    def get_views(self, v_id):
        video_request = self.youtube.videos().list(
            part='statistics',
            id=v_id,
        )
        views = video_request.execute()['items'][0]['statistics']['viewCount']
        return int(views)

    def valid_date(self, yt_date_str):
        yt_date = date.fromisoformat(yt_date_str)
        print(yt_date)
        if all([self.min_date, self.max_date]):
            return date.fromisoformat(self.min_date) <= yt_date <= date.fromisoformat(self.max_date)
        elif self.min_date:
            return yt_date >= date.fromisoformat(self.min_date)
        elif self.min_date:
            return yt_date <= date.fromisoformat(self.max_date)
        else:
            return True

    def link_type_init(self):
        """Initializes the filter depending on the link type"""

        try:
            self.link = re.split('m/', self.link, 1)[1]
        except IndexError as e:
            print(e)
            raise
        if self.link.startswith('channel'):
            channel_id = self.link.split('/')[-1]
            self.channel_request = self.youtube.channels().list(part='contentDetails', id=channel_id)
            title_request = self.youtube.channels().list(part='snippet', id=channel_id)

            self.yt_username = title_request.execute()['items'][0]['snippet']['title']
            self.playlist = self.channel_request.execute()['items'][0]['contentDetails']['relatedPlaylists'][
                'uploads']

        elif self.link.startswith('watch') and '&list=' in self.link:
            self.playlist = re.search(r'(?<=st=).*?(?=&ab)', self.link).group()
            video = re.search(r'(?<=v=).*?(?=&l)', self.link).group()
            video_request = self.youtube.videos().list(part='snippet', id=video, )
            snippet = video_request.execute()['items'][0]['snippet']
            channel_id = snippet['channelId']
            self.yt_username = snippet['channelTitle']
            self.channel_request = self.youtube.channels().list(part='contentDetails', id=channel_id)
        elif self.link.startswith('c/'):
            self.yt_username = re.search(r'(?<=c/).*?(?=/)', self.link).group()
            self.channel_request = self.youtube.channels().list(part='contentDetails', forUsername=self.yt_username)
            self.playlist = self.channel_request.execute()['items'][0]['contentDetails']['relatedPlaylists'][
                'uploads']

        else:
            raise WrongLinkException('Wrong link')

    def search(self):
        while True:
            playlist_request = self.youtube.playlistItems().list(
                part='snippet',
                playlistId=self.playlist,
                maxResults=50,
                pageToken=self.next_page
            )

            pl_response = playlist_request.execute()
            self.portions.append(pl_response)

            date_control = re.match(self.re_date, pl_response['items'][0]['snippet']['publishedAt']).group()

            if self.min_date and date.fromisoformat(date_control) < date.fromisoformat(self.min_date):
                self.next_page = None
                break

            self.videos.update(
                {video: {
                    # dict content
                    'title': value['snippet']['title'],
                    'views': views,
                    'uploaded_at': yt_video_date,
                    'link': f'https://www.youtube.com/watch?v={video}'}

                    # cycle expression
                    for value in pl_response['items']

                    # variables
                    if (video := value['snippet']['resourceId']['videoId'],
                        views := self.get_views(video),
                        yt_video_date := re.match(self.re_date, value['snippet']['publishedAt']).group(),)

                    # conditions
                    if self.valid_date(yt_video_date)
                    if self.min_views <= views < self.max_views}
            )

            if n_p := pl_response.get('nextPageToken'):
                self.next_page = n_p
            else:
                self.next_page = None
                break
        self.sort_keys()

    def sort_keys(self):
        if not self.sort_by_date:
            self.sorted_keys = sorted(self.videos, key=lambda x: self.videos[x]['views'], reverse=not self.ascending)
        else:
            self.sorted_keys = sorted(self.videos,
                                      key=lambda x: date.fromisoformat(self.videos[x]['uploaded_at']),
                                      reverse=not self.ascending)

    @staticmethod
    def readable_line(line: dict):
        return f'{line["title"]}: {line["views"]} - {line["link"]}'

    def print_videos(self):
        for key in self.sorted_keys:
            print(self.readable_line(self.videos[key]))

    def save_to_csv(self):
        with open(f_name := f'{self.yt_username}.csv', 'w', newline='', encoding='utf8') as out_csv:
            video_list = [self.videos[key] for key in self.sorted_keys]
            writer = csv.DictWriter(out_csv, delimiter=',', fieldnames=video_list[0])
            writer.writeheader()
            writer.writerows(video_list)
        return f_name

    def save_to_json(self):
        with open(f_name := f'{self.yt_username}.json', 'w') as json_file:
            json.dump(self.videos, json_file)
        return f_name

    def save_to_txt(self):
        with open(f_name := f"{self.yt_username}.txt", mode='w', encoding='utf8') as text_file:
            if self.videos:
                for key in self.sorted_keys:
                    text_file.write(f'{self.readable_line(self.videos[key])}\n')
                return f_name
            else:
                raise Exception('wtf?')

    def save_to_html(self):
        query_line = 'https://www.youtube.com/results?search_query='
        html = ('<html>'
                '<head><meta charset="utf-8"/></head>'
                '<body><table border="1"><tr><th>Title</th>'
                '<th>Views</th>'
                '<th>Uploaded at</th></tr>')
        html += ''.join(
            f'<tr><td><a target="_blank" href="{query_line}{video["title"].replace(" ", "+")}">{video["title"]}'
            f'</a></td><td>{video["views"]}</td><td>{video["uploaded_at"]}</td></tr>'
            for key in self.sorted_keys
            if (video := self.videos[key]))

        html += '</tr>'
        html += '</table></body></html>'
        with open(f_name := f"{self.yt_username}.html", mode='w', encoding='utf8') as html_file:
            html_file.write(html)
            print(f_name)
        return f_name


class WrongLinkException(Exception):
    pass


if __name__ == '__main__':
    # more than 1000 video
    channel = 'https://www.youtube.com/channel/UCW2nvVd1fOXKld6M6Hvo9tA'

    yt_filter = YouTubeFilter(link=channel,
                              min_views=130000,
                              max_views=300000,
                              min_date='2017-01-01')

    yt_filter.search()
    yt_filter.save_to_html()
    yt_filter.save_to_txt()
    yt_filter.save_to_csv()
    yt_filter.save_to_json()
