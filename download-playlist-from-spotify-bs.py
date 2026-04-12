import json
import os
from datetime import datetime, timedelta, timezone
import requests
import spotipy
import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pathlib import Path
from spotipy.oauth2 import SpotifyOAuth

COL_TRACK_NAME = 'Track Name'
COL_TRACK_URI = 'Track URI'
COL_ARTIST_NAMES = 'Artist Name(s)'
COL_ARTIST_URIS = 'Artist URI(s)'
COL_ALBUM_NAME = 'Album Name'
COL_ADDED_AT = 'Added At'

PLAYLIST_ID = os.getenv('SPOTIFY_DISCOVER_WEEKLY_PLAYLIST_ID')

if not PLAYLIST_ID:
    raise RuntimeError('SPOTIFY_DISCOVER_WEEKLY_PLAYLIST_ID environment variable must be set')

PLAYLIST_URL = f'https://open.spotify.com/playlist/{PLAYLIST_ID}'
EMBED_URL = f'https://open.spotify.com/embed/playlist/{PLAYLIST_ID}'
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/126.0.0.0 Safari/537.36'
    )
}

local_run = os.getenv('LOCAL_RUN', 'false')
if local_run.lower() == 'true':
    load_dotenv()

client_id = os.getenv('SPOTIFY_CLIENT_ID')
client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
redirect_uri = 'http://127.0.0.1:3000'


def fetch_embed_playlist():
    response = requests.get(EMBED_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')
    next_data_tag = soup.find('script', id='__NEXT_DATA__')
    if not next_data_tag or not next_data_tag.string:
        raise RuntimeError('Could not find playlist data in the Spotify embed page HTML')

    data = json.loads(next_data_tag.string)
    entity = data['props']['pageProps']['state']['data']['entity']
    track_list = entity.get('trackList', [])

    tracks = []
    for item in track_list:
        uri = item.get('uri')
        if not uri:
            continue

        tracks.append({
            'uri': uri,
            'name': item.get('title', ''),
            'artist_text': item.get('subtitle', ''),
        })

    return entity, tracks


def get_spotify_client():
    if not client_id or not client_secret:
        raise RuntimeError('SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set')

    cache_path = Path('.cache')
    if not cache_path.is_file() and 'SPOTIFY_AUTH_CACHE' in os.environ:
        auth_cache = os.environ['SPOTIFY_AUTH_CACHE']
        cache_path.write_text(json.dumps(json.loads(auth_cache)), encoding='utf-8')

    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope='user-read-private',
        cache_path=str(cache_path),
    )
    return spotipy.Spotify(auth_manager=auth_manager)


def parse_track_id(uri):
    if not uri:
        return None
    if uri.startswith('spotify:track:'):
        return uri.split(':')[-1]
    if 'open.spotify.com/track/' in uri:
        return uri.split('/track/')[-1].split('?')[0]
    return uri


def chunked(values, size=50):
    for i in range(0, len(values), size):
        yield values[i:i + size]


def get_added_at():
    gmt_minus_3 = timezone(timedelta(hours=-3))
    now = datetime.now(tz=gmt_minus_3)
    monday = now - timedelta(days=now.weekday())
    monday_3am = monday.replace(hour=3, minute=0, second=0, microsecond=0)
    return monday_3am.strftime('%Y-%m-%dT%H:%M:%SZ')


def fetch_track_metadata_api(track_uris):
    spotify = get_spotify_client()
    track_ids = [parse_track_id(uri) for uri in track_uris if parse_track_id(uri)]
    metadata = []

    for batch in chunked(track_ids, 50):
        result = spotify.tracks(batch)
        for track in result.get('tracks', []):
            if not track:
                continue
            metadata.append({
                'uri': track.get('uri', ''),
                'name': track.get('name', ''),
                'artists': track.get('artists', []),
                'album': track.get('album', {}).get('name', ''),
            })

    return metadata


def merge_tracks(embed_tracks, api_tracks):
    api_by_uri = {track['uri']: track for track in api_tracks}
    merged = []

    for embed_track in embed_tracks:
        api_track = api_by_uri.get(embed_track['uri'])
        if api_track:
            artist_names = ','.join([artist.get('name', '') for artist in api_track.get('artists', [])])
            artist_uris = ','.join([artist.get('uri', '') for artist in api_track.get('artists', [])])
            album_name = api_track.get('album', '')
            track_name = api_track.get('name', embed_track.get('name', ''))
        else:
            artist_names = embed_track.get('artist_text', '')
            artist_uris = ''
            album_name = ''
            track_name = embed_track.get('name', '')

        merged.append({
            COL_TRACK_NAME: track_name,
            COL_TRACK_URI: embed_track['uri'],
            COL_ARTIST_NAMES: artist_names,
            COL_ARTIST_URIS: artist_uris,
            COL_ALBUM_NAME: album_name,
            COL_ADDED_AT: get_added_at(),
        })

    return merged


def main():
    entity, embed_tracks = fetch_embed_playlist()

    print(f'Found playlist "{entity.get("name")}" from embed page. ID: {entity.get("id")}')
    if not embed_tracks:
        raise RuntimeError('No tracks were found on the Spotify embed page')

    api_tracks = []
    if client_id and client_secret:
        try:
            api_tracks = fetch_track_metadata_api([track['uri'] for track in embed_tracks])
        except Exception as exc:
            print('Warning: could not fetch full track metadata from Spotify API:', exc)

    playlist_rows = merge_tracks(embed_tracks, api_tracks)
    if not playlist_rows:
        raise RuntimeError('No playlist rows could be generated from embed page data')

    output_folder = Path('output')
    output_folder.mkdir(exist_ok=True)
    output_path = output_folder / 'this-weeks-playlist.csv'

    print('Saving playlist as CSV...')
    pd.DataFrame.from_dict(playlist_rows).to_csv(output_path, index=False)
    print(f'Playlist saved to {output_path}')


if __name__ == '__main__':
    main()
